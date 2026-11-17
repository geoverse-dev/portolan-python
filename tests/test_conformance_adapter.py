"""Tests for the development-only Read Profile adapter."""

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
