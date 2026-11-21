from __future__ import annotations

import json

from portolan import CatalogBuilder, CatalogEditor, CatalogGraph, ManagedDocument, WritePlanner


def _root() -> CatalogGraph:
    return (
        CatalogBuilder(id="demo", spec_version="0.3.0")
        .title("Demo")
        .description("Before")
        .extra_fields({"x-vendor": {"keep": True}})
        .build()
    )


def _collection(key: str = "roads/collection.json") -> ManagedDocument:
    return ManagedDocument(
        key,
        {
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
        },
        "catalog.json",
    )


def test_editor_is_copy_on_write_and_preserves_unknown_fields() -> None:
    original = _root()
    edited = CatalogEditor(original).set_field("catalog.json", "description", "After").build()

    assert original.documents[0].document["description"] == "Before"
    assert edited.documents[0].document["description"] == "After"
    assert edited.documents[0].document["x-vendor"] == {"keep": True}


def test_editor_adds_and_removes_documents_and_assets() -> None:
    with_collection = CatalogEditor(_root()).add_document(_collection()).build()
    with_asset = (
        CatalogEditor(with_collection)
        .set_asset("roads/collection.json", "data", {"href": "roads.parquet", "roles": ["data"]})
        .build()
    )
    without_asset = (
        CatalogEditor(with_asset).remove_asset("roads/collection.json", "data").build()
    )
    without_collection = (
        CatalogEditor(without_asset).remove_document("roads/collection.json").build()
    )

    assert with_asset.documents[1].document["assets"]["data"]["href"] == "roads.parquet"
    assert without_asset.documents[1].document["assets"] == {}
    assert [entry.key for entry in without_collection.documents] == ["catalog.json"]


def test_delta_deletes_only_explicit_prior_managed_metadata() -> None:
    plan = WritePlanner().plan(
        _root(), prior_managed_keys=("catalog.json", "old/collection.json")
    )

    assert [(operation.kind, operation.key) for operation in plan.operations] == [
        ("put", "catalog.json"),
        ("delete", "old/collection.json"),
    ]


def test_unmanaged_files_are_never_inferred_as_deletions() -> None:
    plan = WritePlanner().plan(_root(), prior_managed_keys=("catalog.json",))

    assert all(operation.key != "notes.txt" for operation in plan.operations)


def test_export_prefix_changes_keys_but_not_relative_links() -> None:
    graph = CatalogEditor(_root()).add_document(_collection()).build()
    plan = WritePlanner().plan(graph, key_prefix="exports/v2")
    operations = {operation.key: operation for operation in plan.operations}

    assert set(operations) == {
        "exports/v2/catalog.json",
        "exports/v2/roads/collection.json",
    }
    root = json.loads(operations["exports/v2/catalog.json"].content)
    assert next(link for link in root["links"] if link["rel"] == "child")["href"] == (
        "roads/collection.json"
    )


def test_repeated_planning_is_stable_and_side_effect_free() -> None:
    graph = CatalogEditor(_root()).add_document(_collection()).build()

    assert WritePlanner().plan(graph) == WritePlanner().plan(graph)
