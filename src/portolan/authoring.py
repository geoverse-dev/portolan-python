"""In-memory catalog authoring and storage-independent write planning."""

from __future__ import annotations

import json
import posixpath
from copy import deepcopy
from dataclasses import dataclass
from pathlib import PurePosixPath
from typing import Any

JsonObject = dict[str, Any]
PORTOLAN_SCHEMA_URI = "https://schemas.portolan-sdi.org/portolan/v0.3.0/schema.json"
SUPPORTED_SPEC_VERSION = "0.3.0"


class AuthoringError(ValueError):
    """A stable authoring or planning failure."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class ManagedDocument:
    """One STAC document and its logical output location."""

    key: str
    document: JsonObject
    parent_key: str | None = None
    relation: str = "child"


@dataclass(frozen=True)
class DocumentationEntry:
    """Caller-supplied documentation linked from one managed document."""

    owner_key: str
    key: str
    relation: str
    content: str
    media_type: str = "text/markdown"


@dataclass(frozen=True)
class CatalogGraph:
    """A storage-independent in-memory Portolan catalog graph."""

    spec_version: str
    documents: tuple[ManagedDocument, ...]
    documentation: tuple[DocumentationEntry, ...] = ()

    @classmethod
    def from_dict(cls, value: JsonObject) -> CatalogGraph:
        """Import a graph definition while preserving document fields."""
        spec_version = value.get("spec_version")
        raw_documents = value.get("documents")
        raw_documentation = value.get("documentation", [])
        if not isinstance(spec_version, str) or not isinstance(raw_documents, list):
            raise AuthoringError("INVALID_REQUEST", "spec_version and documents are required")
        if not isinstance(raw_documentation, list):
            raise AuthoringError("INVALID_REQUEST", "documentation must be an array")

        documents: list[ManagedDocument] = []
        for raw in raw_documents:
            if not isinstance(raw, dict):
                raise AuthoringError("INVALID_REQUEST", "each document entry must be an object")
            key = raw.get("key")
            document = raw.get("document")
            parent_key = raw.get("parent_key")
            relation = raw.get("relation", "child")
            if (
                not isinstance(key, str)
                or not isinstance(document, dict)
                or parent_key is not None
                and not isinstance(parent_key, str)
                or not isinstance(relation, str)
            ):
                raise AuthoringError("INVALID_REQUEST", "invalid document entry")
            documents.append(
                ManagedDocument(
                    key=key,
                    document=deepcopy(document),
                    parent_key=parent_key,
                    relation=relation,
                )
            )

        documentation: list[DocumentationEntry] = []
        for raw in raw_documentation:
            if not isinstance(raw, dict):
                raise AuthoringError("INVALID_REQUEST", "documentation entry must be an object")
            owner_key = raw.get("owner_key")
            key = raw.get("key")
            relation = raw.get("rel")
            content = raw.get("content")
            media_type = raw.get("media_type", "text/markdown")
            if (
                not isinstance(owner_key, str)
                or not isinstance(key, str)
                or not isinstance(relation, str)
                or not isinstance(content, str)
                or not isinstance(media_type, str)
            ):
                raise AuthoringError("INVALID_REQUEST", "invalid documentation entry")
            documentation.append(
                DocumentationEntry(
                    owner_key=owner_key,
                    key=key,
                    relation=relation,
                    content=content,
                    media_type=media_type,
                )
            )
        return cls(spec_version, tuple(documents), tuple(documentation))


class CatalogBuilder:
    """Build a root catalog without storage access."""

    def __init__(self, *, id: str, spec_version: str) -> None:
        self._id = id
        self._spec_version = spec_version
        self._title: str | None = None
        self._description: str | None = None
        self._extra_fields: JsonObject = {}

    def title(self, value: str) -> CatalogBuilder:
        self._title = value
        return self

    def description(self, value: str) -> CatalogBuilder:
        self._description = value
        return self

    def extra_fields(self, value: JsonObject) -> CatalogBuilder:
        self._extra_fields = deepcopy(value)
        return self

    def build(self) -> CatalogGraph:
        document: JsonObject = {
            "type": "Catalog",
            "stac_version": "1.1.0",
            "id": self._id,
            "title": self._title,
            "description": self._description,
            **self._extra_fields,
        }
        return CatalogGraph(
            spec_version=self._spec_version,
            documents=(ManagedDocument("catalog.json", document),),
        )


@dataclass(frozen=True)
class PutOperation:
    """One intended metadata or documentation write."""

    key: str
    content: bytes
    kind: str = "put"


@dataclass(frozen=True)
class WritePlan:
    """An immutable snapshot of intended outputs that performs no I/O."""

    spec_version: str
    operations: tuple[PutOperation, ...]


class WritePlanner:
    """Create deterministic PUT-only plans for Portolan 0.3.0 metadata."""

    def plan(self, graph: CatalogGraph) -> WritePlan:
        _preflight(graph)
        documents = [
            ManagedDocument(
                entry.key,
                deepcopy(entry.document),
                entry.parent_key,
                entry.relation,
            )
            for entry in graph.documents
        ]
        by_key = {entry.key: entry for entry in documents}
        root = by_key["catalog.json"]

        for entry in documents:
            extensions = entry.document.get("stac_extensions")
            normalized_extensions = list(extensions) if isinstance(extensions, list) else []
            if PORTOLAN_SCHEMA_URI not in normalized_extensions:
                normalized_extensions.append(PORTOLAN_SCHEMA_URI)
            entry.document["stac_extensions"] = normalized_extensions
            links = _document_links(entry.document)
            links.append(_link("self", PurePosixPath(entry.key).name))
            if entry.key != root.key:
                links.append(_link("root", _relative_href(entry.key, root.key)))
            if entry.parent_key is not None:
                links.append(_link("parent", _relative_href(entry.key, entry.parent_key)))
                parent = by_key[entry.parent_key]
                parent_links = _document_links(parent.document)
                parent_links.append(_link(entry.relation, _relative_href(parent.key, entry.key)))
                parent.document["links"] = parent_links
                if (
                    entry.document.get("type") == "Feature"
                    and parent.document.get("type") == "Collection"
                ):
                    links.append(_link("collection", _relative_href(entry.key, parent.key)))
            entry.document["links"] = links

        for documentation in graph.documentation:
            owner = by_key[documentation.owner_key]
            links = _document_links(owner.document)
            links.append(
                _link(
                    documentation.relation,
                    _relative_href(owner.key, documentation.key),
                    documentation.media_type,
                )
            )
            owner.document["links"] = links

        operations = [
            PutOperation(entry.key, serialize_document(_with_normalized_links(entry.document)))
            for entry in documents
        ]
        operations.extend(
            PutOperation(entry.key, entry.content.encode("utf-8"))
            for entry in graph.documentation
        )
        return WritePlan(graph.spec_version, tuple(sorted(operations, key=lambda item: item.key)))


def serialize_document(document: JsonObject) -> bytes:
    """Serialize one document deterministically as UTF-8 JSON."""
    return (
        json.dumps(document, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"
    ).encode("utf-8")


def _preflight(graph: CatalogGraph) -> None:
    if graph.spec_version != SUPPORTED_SPEC_VERSION:
        raise AuthoringError("UNSUPPORTED_SPEC_VERSION", "only Portolan 0.3.0 is supported")
    keys = [entry.key for entry in graph.documents] + [entry.key for entry in graph.documentation]
    if len(keys) != len(set(keys)):
        raise AuthoringError("DUPLICATE_OUTPUT_KEY", "logical output keys must be unique")
    if any(not _safe_output_key(key) for key in keys):
        raise AuthoringError("INVALID_OUTPUT_PATH", "output keys must be relative POSIX paths")
    by_key = {entry.key: entry for entry in graph.documents}
    root = by_key.get("catalog.json")
    if root is None or root.document.get("type") != "Catalog":
        raise AuthoringError("MISSING_REQUIRED_METADATA", "catalog.json root is required")
    for document_entry in graph.documents:
        _require_metadata(document_entry.document)
        if document_entry.parent_key is not None and document_entry.parent_key not in by_key:
            raise AuthoringError("MISSING_REQUIRED_METADATA", "document parent is not managed")
        if document_entry.relation not in {"child", "item"}:
            raise AuthoringError("INVALID_REQUEST", "relation must be child or item")
    for documentation_entry in graph.documentation:
        if documentation_entry.owner_key not in by_key:
            raise AuthoringError("MISSING_REQUIRED_METADATA", "documentation owner is not managed")


def _require_metadata(document: JsonObject) -> None:
    document_type = document.get("type")
    required = {"type", "stac_version", "id"}
    if document_type in {"Catalog", "Collection"}:
        required.update({"title", "description"})
    elif document_type == "Feature":
        required.update({"collection", "properties"})
    else:
        raise AuthoringError("MISSING_REQUIRED_METADATA", "unsupported STAC document type")
    if any(document.get(field) is None or document.get(field) == "" for field in required):
        raise AuthoringError("MISSING_REQUIRED_METADATA", "required STAC metadata is missing")


def _document_links(document: JsonObject) -> list[JsonObject]:
    links = document.get("links")
    if links is None:
        return []
    if not isinstance(links, list) or any(not isinstance(link, dict) for link in links):
        raise AuthoringError("WRITE_ERROR", "links must be an array of objects")
    return [deepcopy(link) for link in links]


def _with_normalized_links(document: JsonObject) -> JsonObject:
    normalized = deepcopy(document)
    links = _document_links(normalized)
    unique: dict[tuple[str, str], JsonObject] = {}
    for link in links:
        relation = link.get("rel")
        href = link.get("href")
        if not isinstance(relation, str) or not isinstance(href, str):
            raise AuthoringError("WRITE_ERROR", "links require rel and href strings")
        unique.setdefault((relation, href), link)
    normalized["links"] = [unique[key] for key in sorted(unique)]
    return normalized


def _link(relation: str, href: str, media_type: str = "application/json") -> JsonObject:
    return {"rel": relation, "href": href, "type": media_type}


def _relative_href(owner_key: str, target_key: str) -> str:
    owner_directory = posixpath.dirname(owner_key) or "."
    return posixpath.relpath(target_key, owner_directory)


def _safe_output_key(value: str) -> bool:
    if not value or "\\" in value:
        return False
    path = PurePosixPath(value)
    return (
        not path.is_absolute()
        and path.as_posix() == value
        and all(part not in {"", ".", ".."} for part in path.parts)
    )
