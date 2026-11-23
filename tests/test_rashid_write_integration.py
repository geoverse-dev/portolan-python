"""Independent normative validation of catalogs written by the SDK."""

from __future__ import annotations

from pathlib import Path

import pytest

from portolan import Catalog, CatalogGraph, WritePlanner

rashid = pytest.importorskip(
    "rashid",
    reason="Rashid 0.4.0 requires Python 3.11 or newer",
)


def _conforming_graph() -> CatalogGraph:
    readme = "# Roads\n\nLicensed under CC-BY-4.0. Source: Example producer.\n"
    agents = "# Catalog guidance\n\nRead catalog.json before following child links.\n"
    return CatalogGraph.from_dict(
        {
            "spec_version": "0.3.0",
            "documents": [
                {
                    "key": "catalog.json",
                    "document": {
                        "type": "Catalog",
                        "stac_version": "1.1.0",
                        "id": "sdk-rashid-integration",
                        "title": "SDK Rashid integration",
                        "description": "A catalog written by portolan-python.",
                    },
                },
                {
                    "key": "roads/collection.json",
                    "parent_key": "catalog.json",
                    "document": {
                        "type": "Collection",
                        "stac_version": "1.1.0",
                        "id": "roads",
                        "title": "Roads",
                        "description": "Road centerlines published for integration testing.",
                        "license": "CC-BY-4.0",
                        "providers": [
                            {
                                "name": "Example producer",
                                "roles": ["producer", "host"],
                                "url": "https://example.test/",
                            }
                        ],
                        "extent": {
                            "spatial": {"bbox": [[-59.0, -38.0, -58.0, -37.0]]},
                            "temporal": {"interval": [[None, None]]},
                        },
                        "assets": {
                            "data": {
                                "href": "https://example.test/roads.parquet",
                                "type": "application/vnd.apache.parquet",
                                "roles": ["data", "source"],
                                "title": "Road centerlines",
                                "description": "GeoParquet road centerlines.",
                            }
                        },
                    },
                },
            ],
            "documentation": [
                {
                    "owner_key": "catalog.json",
                    "key": "README.md",
                    "rel": "describedby",
                    "content": readme,
                },
                {
                    "owner_key": "catalog.json",
                    "key": "AGENTS.md",
                    "rel": "agents",
                    "content": agents,
                },
                {
                    "owner_key": "roads/collection.json",
                    "key": "roads/README.md",
                    "rel": "describedby",
                    "content": readme,
                },
                {
                    "owner_key": "roads/collection.json",
                    "key": "roads/AGENTS.md",
                    "rel": "agents",
                    "content": agents,
                },
            ],
        }
    )


def _materialize(graph: CatalogGraph, target: Path) -> None:
    for operation in WritePlanner().plan(graph).operations:
        assert operation.kind == "put"
        output = target / operation.key
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_bytes(operation.content)


def _validate(target: Path):  # type: ignore[no-untyped-def]
    options = rashid.ValidationOptions(schema=True, data=False, live=False)
    return rashid.validate(target, options=options)


@pytest.mark.integration
def test_written_catalog_passes_rashid_and_can_be_reopened(tmp_path: Path) -> None:
    _materialize(_conforming_graph(), tmp_path)

    catalog = Catalog.open(tmp_path)
    report = _validate(tmp_path)

    assert catalog.id == "sdk-rashid-integration"
    assert [collection.id for collection in catalog.collections()] == ["roads"]
    assert report.errors == []
    assert {"metadata", "structural", "extensions", "schema"}.issubset(report.passes)


@pytest.mark.integration
def test_rashid_detects_missing_generated_documentation(tmp_path: Path) -> None:
    _materialize(_conforming_graph(), tmp_path)
    (tmp_path / "roads" / "AGENTS.md").unlink()

    report = _validate(tmp_path)

    assert not report.passed
    assert {finding.rule_id for finding in report.errors} >= {"PTL-FIL-001"}
