"""Tests for the development-only conformance adapter."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

pytestmark = pytest.mark.unit


def _invoke(request: object) -> dict[str, Any]:
    process = subprocess.run(
        [sys.executable, str(Path(__file__).with_name("conformance_adapter.py"))],
        input=json.dumps(request),
        text=True,
        capture_output=True,
        check=False,
    )
    assert process.returncode == 0
    assert process.stderr == ""
    value = json.loads(process.stdout)
    assert isinstance(value, dict)
    return value


def test_adapter_delegates_document_reading_to_sdk(tmp_path: Path) -> None:
    path = tmp_path / "catalog.json"
    document: dict[str, Any] = {
        "type": "Catalog",
        "id": "á",
        "links": [],
        "unknown": None,
    }
    path.write_text(json.dumps(document), encoding="utf-8")

    response = _invoke(
        {"protocol_version": "1", "operation": "document", "uri": path.as_uri()}
    )

    assert response == {"status": "ok", "result": {"document": document}}


def test_adapter_delegates_write_planning_to_sdk() -> None:
    response = _invoke(
        {
            "protocol_version": "1",
            "operation": "plan_write",
            "input": {
                "spec_version": "0.3.0",
                "documents": [
                    {
                        "key": "catalog.json",
                        "document": {
                            "type": "Catalog",
                            "stac_version": "1.1.0",
                            "id": "demo",
                            "title": "Demo",
                            "description": "Demo catalog.",
                        },
                    }
                ],
            },
        }
    )

    assert response["status"] == "ok"
    assert response["result"]["profile_version"] == "1.1"
    assert response["result"]["spec_version"] == "0.3.0"
    assert [operation["key"] for operation in response["result"]["operations"]] == [
        "catalog.json"
    ]


def test_adapter_distinguishes_direct_and_recursive_items(tmp_path: Path) -> None:
    collection = tmp_path / "collection.json"
    year = tmp_path / "years" / "2025" / "catalog.json"
    item = tmp_path / "years" / "2025" / "item.json"
    year.parent.mkdir(parents=True)
    collection.write_text(
        json.dumps(
            {
                "type": "Collection",
                "id": "observations",
                "links": [{"rel": "child", "href": "years/2025/catalog.json"}],
            }
        ),
        encoding="utf-8",
    )
    year.write_text(
        json.dumps(
            {
                "type": "Catalog",
                "id": "2025",
                "links": [{"rel": "item", "href": "item.json"}],
            }
        ),
        encoding="utf-8",
    )
    item.write_text(
        json.dumps({"type": "Feature", "id": "observation-2025", "links": []}),
        encoding="utf-8",
    )

    direct = _invoke(
        {"protocol_version": "1", "operation": "items", "uri": collection.as_uri()}
    )
    recursive = _invoke(
        {
            "protocol_version": "1",
            "operation": "items_recursive",
            "uri": collection.as_uri(),
        }
    )

    assert direct == {"status": "ok", "result": {"entries": []}}
    assert recursive == {
        "status": "ok",
        "result": {"entries": [{"id": "observation-2025", "uri": item.as_uri()}]},
    }


@pytest.mark.parametrize(
    ("payload", "code"),
    [
        ({"protocol_version": "2", "operation": "inspect", "uri": "file:///x"},
         "UNSUPPORTED_PROTOCOL"),
        ({"protocol_version": "1", "operation": "unknown", "uri": "file:///x"},
         "UNSUPPORTED_OPERATION"),
        ({"protocol_version": "1", "operation": "inspect"}, "INVALID_REQUEST"),
    ],
)
def test_adapter_returns_stable_domain_errors(payload: object, code: str) -> None:
    assert _invoke(payload) == {"status": "error", "error": {"code": code}}
