"""Command-line adapter for the Portolan SDK Read Profile v1 test suite."""

from __future__ import annotations

import json
import sys
import tempfile
from json import JSONDecodeError
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError

from portolan import (
    AuthoringError,
    Catalog,
    CatalogEditor,
    CatalogGraph,
    Collection,
    DocumentationEntry,
    ManagedDocument,
    StacDocument,
    WritePlanner,
    open_document,
)

JsonObject = dict[str, Any]
OPERATIONS = frozenset(
    {
        "document",
        "inspect",
        "children",
        "collections",
        "items",
        "items_recursive",
        "assets",
        "links",
        "plan_write",
        "edit_plan",
        "roundtrip",
    }
)


def _entry(document: StacDocument) -> JsonObject:
    return {"id": document.id, "uri": document.href}


def _linked_entries(document: StacDocument, relation: str) -> list[JsonObject]:
    entries = []
    for link in document.links():
        if link.rel == relation:
            entries.append(_entry(open_document(link.href)))
    return sorted(entries, key=lambda entry: (entry["id"], entry["uri"]))


def _extra_fields(raw: JsonObject, known: set[str]) -> JsonObject:
    return {key: value for key, value in raw.items() if key not in known}


def _operate(operation: str, uri: str) -> JsonObject:
    document = open_document(uri)
    if operation == "document":
        return {"document": document.data}
    if operation == "inspect":
        return {
            "type": document.type,
            "id": document.id,
            "title": document.title,
            "description": document.description,
            "stac_version": document.stac_version,
            "stac_extensions": list(document.stac_extensions),
        }
    if operation == "children":
        return {"entries": _linked_entries(document, "child")}
    if operation == "collections":
        if not isinstance(document, Catalog):
            return {"entries": []}
        entries = [_entry(collection) for collection in document.collections()]
        return {"entries": sorted(entries, key=lambda entry: (entry["id"], entry["uri"]))}
    if operation == "items":
        return {"entries": _linked_entries(document, "item")}
    if operation == "items_recursive":
        if not isinstance(document, (Catalog, Collection)):
            return {"entries": []}
        entries = [_entry(open_document(link.href)) for link in document.item_links()]
        return {"entries": sorted(entries, key=lambda entry: (entry["id"], entry["uri"]))}
    if operation == "assets":
        raw_assets = document.data.get("assets")
        entries = []
        if isinstance(raw_assets, dict):
            assets_by_key = {asset.key: asset for asset in document.assets()}
            for key, raw in raw_assets.items():
                valid_asset = (
                    isinstance(key, str) and isinstance(raw, dict) and key in assets_by_key
                )
                if not valid_asset:
                    continue
                asset = assets_by_key[key]
                roles = raw.get("roles", [])
                entries.append(
                    {
                        "key": key,
                        "href": asset.original_href,
                        "resolved_href": asset.href,
                        "type": raw.get("type") if isinstance(raw.get("type"), str) else None,
                        "roles": roles if isinstance(roles, list) else [],
                        "title": raw.get("title") if isinstance(raw.get("title"), str) else None,
                        "description": raw.get("description")
                        if isinstance(raw.get("description"), str)
                        else None,
                        "extra_fields": _extra_fields(
                            raw, {"href", "type", "roles", "title", "description"}
                        ),
                    }
                )
        return {"entries": sorted(entries, key=lambda entry: entry["key"])}
    if operation == "links":
        entries = []
        for link in document.links():
            entries.append(
                {
                    "rel": link.rel,
                    "href": link.original_href,
                    "resolved_href": link.href,
                    "type": link.media_type,
                    "title": link.title,
                    "extra_fields": _extra_fields(link.raw, {"rel", "href", "type", "title"}),
                }
            )
        return {"entries": sorted(entries, key=lambda entry: (entry["rel"], entry["href"]))}
    raise ValueError("UNSUPPORTED_OPERATION")


def _request(value: object) -> JsonObject:
    if not isinstance(value, dict):
        raise ValueError("INVALID_REQUEST")
    if value.get("protocol_version") != "1":
        raise ValueError("UNSUPPORTED_PROTOCOL")
    operation = value.get("operation")
    if not isinstance(operation, str):
        raise ValueError("INVALID_REQUEST")
    if operation not in OPERATIONS:
        raise ValueError("UNSUPPORTED_OPERATION")
    if operation in {"plan_write", "edit_plan", "roundtrip"}:
        input_value = value.get("input")
        if not isinstance(input_value, dict) or "uri" in value:
            raise ValueError("INVALID_REQUEST")
        graph_value = input_value.get("graph", input_value)
        if not isinstance(graph_value, dict):
            raise ValueError("INVALID_REQUEST")
        graph = CatalogGraph.from_dict(graph_value)
        if operation != "plan_write":
            graph = _apply_changes(graph, input_value.get("changes", []))
        prior = input_value.get("prior_managed_keys", [])
        prefix = input_value.get("key_prefix", "")
        if not isinstance(prior, list) or not all(isinstance(key, str) for key in prior):
            raise ValueError("INVALID_REQUEST")
        if not isinstance(prefix, str):
            raise ValueError("INVALID_REQUEST")
        plan = WritePlanner().plan(
            graph, prior_managed_keys=tuple(prior), key_prefix=prefix
        )
        if operation == "roundtrip":
            return _roundtrip(plan)
        return {
            "profile_version": "1.1",
            "spec_version": plan.spec_version,
            "operations": [
                _plan_operation(operation)
                for operation in plan.operations
            ],
        }
    uri = value.get("uri")
    if not isinstance(uri, str) or not uri or "input" in value:
        raise ValueError("INVALID_REQUEST")
    return _operate(operation, uri)


def _apply_changes(graph: CatalogGraph, changes: object) -> CatalogGraph:
    if not isinstance(changes, list):
        raise ValueError("INVALID_REQUEST")
    editor = CatalogEditor(graph)
    for change in changes:
        if not isinstance(change, dict):
            raise ValueError("INVALID_REQUEST")
        kind = change.get("kind")
        key = change.get("key")
        if not isinstance(kind, str) or not isinstance(key, str):
            raise ValueError("INVALID_REQUEST")
        if kind == "set_field":
            field = change.get("field")
            if not isinstance(field, str) or "value" not in change:
                raise ValueError("INVALID_REQUEST")
            editor.set_field(key, field, change["value"])
        elif kind == "add_document":
            document = change.get("document")
            parent_key = change.get("parent_key")
            relation = change.get("relation", "child")
            link_title = change.get("link_title")
            if not isinstance(document, dict) or not isinstance(relation, str):
                raise ValueError("INVALID_REQUEST")
            if parent_key is not None and not isinstance(parent_key, str):
                raise ValueError("INVALID_REQUEST")
            if link_title is not None and not isinstance(link_title, str):
                raise ValueError("INVALID_REQUEST")
            editor.add_document(
                ManagedDocument(key, document, parent_key, relation, link_title)
            )
        elif kind == "remove_document":
            editor.remove_document(key)
        elif kind == "set_asset":
            asset_key = change.get("asset_key")
            asset = change.get("asset")
            if not isinstance(asset_key, str) or not isinstance(asset, dict):
                raise ValueError("INVALID_REQUEST")
            editor.set_asset(key, asset_key, asset)
        elif kind == "remove_asset":
            asset_key = change.get("asset_key")
            if not isinstance(asset_key, str):
                raise ValueError("INVALID_REQUEST")
            editor.remove_asset(key, asset_key)
        elif kind == "set_documentation":
            owner_key = change.get("owner_key")
            relation = change.get("rel")
            content = change.get("content")
            media_type = change.get("media_type", "text/markdown")
            if (
                not isinstance(owner_key, str)
                or not isinstance(relation, str)
                or not isinstance(content, str)
                or not isinstance(media_type, str)
            ):
                raise ValueError("INVALID_REQUEST")
            editor.set_documentation(
                DocumentationEntry(owner_key, key, relation, content, media_type)
            )
        elif kind == "remove_documentation":
            editor.remove_documentation(key)
        else:
            raise ValueError("INVALID_REQUEST")
    return editor.build()


def _plan_operation(operation: Any) -> JsonObject:
    kind = operation.kind
    key = operation.key
    result: JsonObject = {"kind": kind, "key": key}
    content = getattr(operation, "content", None)
    if kind == "put" and isinstance(content, bytes):
        result["content"] = content.decode("utf-8")
    return result


def _roundtrip(plan: Any) -> JsonObject:
    operations = plan.operations
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        for operation in operations:
            content = getattr(operation, "content", None)
            if not isinstance(content, bytes):
                continue
            target = root / operation.key
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(content)
        documents = []
        documentation = []
        for operation in operations:
            key = operation.key
            if operation.kind != "put":
                continue
            if not key.endswith(".json"):
                documentation.append(
                    {"key": key, "content": operation.content.decode("utf-8")}
                )
                continue
            document = open_document(root / key)
            documents.append({"key": key, "document": document.data})
    result: JsonObject = {"profile_version": "1.1", "documents": documents}
    if documentation:
        result["documentation"] = documentation
    return result


def _error_code(error: Exception) -> str:
    if isinstance(error, AuthoringError):
        return error.code
    message = str(error)
    if message in {"INVALID_REQUEST", "UNSUPPORTED_PROTOCOL", "UNSUPPORTED_OPERATION"}:
        return message
    if isinstance(error, FileNotFoundError) or isinstance(error, HTTPError) and error.code == 404:
        return "NOT_FOUND"
    if isinstance(error, JSONDecodeError):
        return "INVALID_JSON"
    if isinstance(error, (HTTPError, URLError, OSError)):
        return "READ_ERROR"
    if isinstance(error, ValueError) and message.startswith("Unsupported URI scheme"):
        return "UNSUPPORTED_PROTOCOL"
    return "READ_ERROR"


def main() -> int:
    try:
        try:
            request = json.loads(sys.stdin.readline())
        except JSONDecodeError as error:
            raise ValueError("INVALID_REQUEST") from error
        response: JsonObject = {"status": "ok", "result": _request(request)}
    except Exception as error:  # Adapter boundary translates SDK and transport errors.
        response = {"status": "error", "error": {"code": _error_code(error)}}
    print(json.dumps(response, ensure_ascii=False, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
