"""Command-line adapter for the Portolan SDK Read Profile v1 test suite."""

from __future__ import annotations

import json
import sys
from json import JSONDecodeError
from typing import Any
from urllib.error import HTTPError, URLError

from portolan import (
    AuthoringError,
    Catalog,
    CatalogGraph,
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
        "assets",
        "links",
        "plan_write",
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
    if operation == "plan_write":
        input_value = value.get("input")
        if not isinstance(input_value, dict) or "uri" in value:
            raise ValueError("INVALID_REQUEST")
        plan = WritePlanner().plan(CatalogGraph.from_dict(input_value))
        return {
            "profile_version": "1",
            "spec_version": plan.spec_version,
            "operations": [
                {
                    "kind": operation.kind,
                    "key": operation.key,
                    "content": operation.content.decode("utf-8"),
                }
                for operation in plan.operations
            ],
        }
    uri = value.get("uri")
    if not isinstance(uri, str) or not uri or "input" in value:
        raise ValueError("INVALID_REQUEST")
    return _operate(operation, uri)


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
