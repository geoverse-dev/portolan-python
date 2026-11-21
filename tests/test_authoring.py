from __future__ import annotations

import json
from pathlib import Path

import pytest

from portolan import Catalog
from portolan.authoring import AuthoringError, CatalogBuilder, CatalogGraph, WritePlanner


def _collection() -> dict[str, object]:
    return {
        "type": "Collection",
        "stac_version": "1.1.0",
        "id": "roads",
        "title": "Roads",
        "description": "Road data.",
        "license": "CC-BY-4.0",
        "extent": {
            "spatial": {"bbox": [[-59, -38, -58, -37]]},
            "temporal": {"interval": [[None, None]]},
        },
        "assets": {
            "data": {
                "href": "roads.parquet",
                "type": "application/vnd.apache.parquet",
                "roles": ["data"],
            }
        },
    }


def test_builder_creates_an_in_memory_graph_and_plan_without_io(tmp_path: Path) -> None:
    graph = (
        CatalogBuilder(id="demo", spec_version="0.3.0")
        .title("Demo catalog")
        .description("An in-memory catalog.")
        .build()
    )

    plan = WritePlanner().plan(graph)

    assert [operation.key for operation in plan.operations] == ["catalog.json"]
    assert json.loads(plan.operations[0].content) == {
        "description": "An in-memory catalog.",
        "id": "demo",
        "links": [{"href": "catalog.json", "rel": "self", "type": "application/json"}],
        "stac_extensions": [
            "https://schemas.portolan-sdi.org/portolan/v0.3.0/schema.json"
        ],
        "stac_version": "1.1.0",
        "title": "Demo catalog",
        "type": "Catalog",
    }
    assert list(tmp_path.iterdir()) == []


def test_graph_import_preserves_unknown_fields_and_builds_structural_links() -> None:
    graph = CatalogGraph.from_dict(
        {
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
                        "x-vendor": {"enabled": True, "values": [1, None, "á"]},
                    },
                },
                {
                    "key": "vectors/roads/collection.json",
                    "parent_key": "catalog.json",
                    "document": _collection(),
                },
            ],
        }
    )

    operations = {operation.key: operation for operation in WritePlanner().plan(graph).operations}
    root = json.loads(operations["catalog.json"].content)
    collection = json.loads(operations["vectors/roads/collection.json"].content)

    assert root["x-vendor"] == {"enabled": True, "values": [1, None, "á"]}
    assert {link["rel"]: link["href"] for link in root["links"]} == {
        "child": "vectors/roads/collection.json",
        "self": "catalog.json",
    }
    assert {link["rel"]: link["href"] for link in collection["links"]} == {
        "parent": "../../catalog.json",
        "root": "../../catalog.json",
        "self": "collection.json",
    }


def test_plan_can_be_materialized_by_a_caller_and_reopened(tmp_path: Path) -> None:
    graph = CatalogGraph.from_dict(
        {
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
                },
                {
                    "key": "roads/collection.json",
                    "parent_key": "catalog.json",
                    "document": _collection(),
                },
            ],
            "documentation": [
                {
                    "owner_key": "catalog.json",
                    "key": "README.md",
                    "rel": "describedby",
                    "content": "# Demo\n",
                }
            ],
        }
    )

    for operation in WritePlanner().plan(graph).operations:
        target = tmp_path / operation.key
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(operation.content)

    catalog = Catalog.open(tmp_path)
    assert catalog.id == "demo"
    assert [collection.id for collection in catalog.collections()] == ["roads"]
    assert (tmp_path / "README.md").read_text(encoding="utf-8") == "# Demo\n"


@pytest.mark.parametrize(
    ("definition", "code"),
    [
        (
            {
                "spec_version": "0.3.0",
                "documents": [
                    {
                        "key": "catalog.json",
                        "document": {
                            "type": "Catalog",
                            "stac_version": "1.1.0",
                            "id": "demo",
                            "description": "Missing title.",
                        },
                    }
                ],
            },
            "MISSING_REQUIRED_METADATA",
        ),
        (
            {
                "spec_version": "0.3.0",
                "documents": [
                    {"key": "catalog.json", "document": {}},
                    {"key": "catalog.json", "document": {}},
                ],
            },
            "DUPLICATE_OUTPUT_KEY",
        ),
        (
            {
                "spec_version": "0.3.0",
                "documents": [
                    {
                        "key": "../catalog.json",
                        "document": {},
                    }
                ],
            },
            "INVALID_OUTPUT_PATH",
        ),
    ],
)
def test_preflight_errors_are_stable(definition: dict[str, object], code: str) -> None:
    with pytest.raises(AuthoringError) as raised:
        WritePlanner().plan(CatalogGraph.from_dict(definition))

    assert raised.value.code == code
