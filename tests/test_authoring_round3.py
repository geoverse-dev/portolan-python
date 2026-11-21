from __future__ import annotations

import json

import pytest

from portolan import AuthoringError, CatalogBuilder, CatalogEditor, CatalogGraph, WritePlanner


def _root(extra: dict[str, object] | None = None) -> CatalogGraph:
    return (
        CatalogBuilder(id="demo", spec_version="0.3.0")
        .title("Demo")
        .description("Catalog")
        .extra_fields(extra or {})
        .build()
    )


def test_unicode_null_numbers_and_unknown_nested_fields_survive_planning() -> None:
    graph = _root(
        {
            "x-vendor": {
                "unicode": "Córdoba",
                "null": None,
                "integer": 1,
                "decimal": 1.5,
                "values": [True, 2, None],
            }
        }
    )

    document = json.loads(WritePlanner().plan(graph).operations[0].content)

    assert document["x-vendor"] == graph.documents[0].document["x-vendor"]


def test_duplicate_authored_links_are_normalized_without_mutating_source() -> None:
    links = [
        {"rel": "describedby", "href": "README.md", "type": "text/markdown"},
        {"rel": "describedby", "href": "README.md", "type": "text/markdown"},
    ]
    graph = _root({"links": links})

    document = json.loads(WritePlanner().plan(graph).operations[0].content)

    assert sum(link["rel"] == "describedby" for link in document["links"]) == 1
    assert graph.documents[0].document["links"] == links


def test_repeated_planning_of_large_tree_is_deterministic() -> None:
    editor = CatalogEditor(_root())
    for number in range(100):
        editor.add_document(
            CatalogGraph.from_dict(
                {
                    "spec_version": "0.3.0",
                    "documents": [
                        {
                            "key": f"collections/{number}/collection.json",
                            "parent_key": "catalog.json",
                            "document": {
                                "type": "Collection",
                                "stac_version": "1.1.0",
                                "id": f"collection-{number}",
                                "title": f"Collection {number}",
                                "description": "Data.",
                                "license": "CC-BY-4.0",
                                "extent": {},
                            },
                        }
                    ],
                }
            ).documents[0]
        )
    graph = editor.build()

    first = WritePlanner().plan(graph)
    second = WritePlanner().plan(graph)

    assert first == second
    assert len(first.operations) == 101


def test_serialization_failure_keeps_original_graph_unchanged() -> None:
    unsupported = object()
    graph = _root({"x-unsupported": unsupported})
    original_value = graph.documents[0].document["x-unsupported"]

    with pytest.raises(AuthoringError, match="serialize") as raised:
        WritePlanner().plan(graph)

    assert raised.value.code == "WRITE_ERROR"
    assert graph.documents[0].document["x-unsupported"] is original_value


def test_mixed_profile_version_is_rejected_explicitly() -> None:
    graph = CatalogBuilder(id="old", spec_version="0.2.0").title("Old").description("Old").build()

    with pytest.raises(AuthoringError) as raised:
        WritePlanner().plan(graph)

    assert raised.value.code == "UNSUPPORTED_SPEC_VERSION"
