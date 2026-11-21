"""Catalog domain API tests."""

from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

import pytest

from portolan import (
    AssetFormat,
    Catalog,
    Collection,
    Item,
    Validator,
    is_stac_metadata,
    open_document,
)

pytestmark = pytest.mark.unit


def _write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")


def test_open_catalog_traverses_collections_items_and_assets(tmp_path: Path) -> None:
    _write_json(
        tmp_path / "catalog.json",
        {
            "type": "Catalog",
            "stac_version": "1.1.0",
            "id": "demo",
            "description": "Demo catalog",
            "links": [
                {"rel": "child", "href": "./roads/collection.json", "type": "application/json"}
            ],
        },
    )
    _write_json(
        tmp_path / "roads" / "collection.json",
        {
            "type": "Collection",
            "stac_version": "1.1.0",
            "id": "roads",
            "description": "Roads",
            "license": "CC-BY-4.0",
            "extent": {
                "spatial": {"bbox": [[-71.0, -35.0, -70.0, -34.0]]},
                "temporal": {"interval": [[None, None]]},
            },
            "links": [{"rel": "item", "href": "./road-1/road-1.json"}],
            "assets": {
                "data": {
                    "href": "./roads.parquet",
                    "type": "application/vnd.apache.parquet",
                    "roles": ["data"],
                }
            },
        },
    )
    _write_json(
        tmp_path / "roads" / "road-1" / "road-1.json",
        {
            "type": "Feature",
            "stac_version": "1.1.0",
            "id": "road-1",
            "collection": "roads",
            "geometry": None,
            "bbox": [-71.0, -35.0, -70.0, -34.0],
            "properties": {"datetime": None},
            "links": [],
            "assets": {
                "data": {
                    "href": "./road-1.parquet",
                    "type": "application/vnd.apache.parquet",
                    "roles": ["data"],
                }
            },
        },
    )

    catalog = Catalog.open(tmp_path / "catalog.json")
    collections = list(catalog.collections())
    items = list(collections[0].items())
    collection_assets = list(collections[0].assets())
    item_assets = list(items[0].assets())

    assert catalog.id == "demo"
    assert [collection.id for collection in collections] == ["roads"]
    assert [item.id for item in items] == ["road-1"]
    assert collection_assets[0].href == (tmp_path / "roads" / "roads.parquet").as_uri()
    assert collection_assets[0].media_type == "application/vnd.apache.parquet"
    assert collection_assets[0].format is AssetFormat.GEOPARQUET
    assert collection_assets[0].roles == ("data",)
    assert item_assets[0].href == (tmp_path / "roads" / "road-1" / "road-1.parquet").as_uri()


def test_catalog_traverses_nested_child_catalogs(tmp_path: Path) -> None:
    _write_json(
        tmp_path / "catalog.json",
        {
            "type": "Catalog",
            "stac_version": "1.1.0",
            "id": "root",
            "description": "Root catalog",
            "links": [
                {"rel": "child", "href": "./transport/catalog.json", "type": "application/json"}
            ],
        },
    )
    _write_json(
        tmp_path / "transport" / "catalog.json",
        {
            "type": "Catalog",
            "stac_version": "1.1.0",
            "id": "transport",
            "description": "Transport catalog",
            "links": [{"rel": "child", "href": "./roads/collection.json"}],
        },
    )
    _write_json(
        tmp_path / "transport" / "roads" / "collection.json",
        {
            "type": "Collection",
            "stac_version": "1.1.0",
            "id": "roads",
            "description": "Roads",
            "license": "CC-BY-4.0",
            "extent": {
                "spatial": {"bbox": [[-71.0, -35.0, -70.0, -34.0]]},
                "temporal": {"interval": [[None, None]]},
            },
            "links": [],
        },
    )

    catalog = Catalog.open(tmp_path)

    assert [collection.id for collection in catalog.collections()] == ["roads"]


def test_catalog_item_links_descend_child_catalogs_but_not_collections(tmp_path: Path) -> None:
    _write_json(
        tmp_path / "catalog.json",
        {
            "type": "Catalog",
            "id": "organizer",
            "links": [
                {"rel": "item", "href": "./root-item.json"},
                {"rel": "child", "href": "./nested/catalog.json"},
                {"rel": "child", "href": "./roads/collection.json"},
            ],
        },
    )
    _write_json(
        tmp_path / "nested" / "catalog.json",
        {
            "type": "Catalog",
            "id": "nested",
            "links": [{"rel": "item", "href": "./nested-item.json"}],
        },
    )
    _write_json(
        tmp_path / "roads" / "collection.json",
        {"type": "Collection", "id": "roads", "links": [{"rel": "item", "href": "./road.json"}]},
    )

    catalog = Catalog.open(tmp_path)

    assert [link.raw["href"] for link in catalog.item_links()] == [
        "./root-item.json",
        "./nested-item.json",
    ]
    assert [link.href for link in catalog.item_links()] == [
        (tmp_path / "root-item.json").as_uri(),
        (tmp_path / "nested" / "nested-item.json").as_uri(),
    ]


def test_collection_item_links_preserve_written_href_and_resolve_against_owner() -> None:
    collection = Collection(
        {
            "type": "Collection",
            "id": "roads",
            "links": [
                {
                    "rel": "item",
                    "href": "./items/road-a.json",
                    "type": "application/geo+json",
                }
            ],
        },
        "https://example.test/catalog/roads/collection.json",
    )

    [link] = list(collection.item_links())

    assert link.raw["href"] == "./items/road-a.json"
    assert link.href == "https://example.test/catalog/roads/items/road-a.json"
    assert link.media_type == "application/geo+json"
    assert link.original_href == "./items/road-a.json"


def test_remote_links_resolve_against_final_url_after_redirect() -> None:
    catalog_bytes = json.dumps(
        {
            "type": "Catalog",
            "id": "root",
            "links": [{"rel": "child", "href": "collection.json"}],
        }
    ).encode()
    collection_bytes = json.dumps(
        {"type": "Collection", "id": "roads", "links": []}
    ).encode()

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802
            if self.path == "/entry":
                self.send_response(302)
                self.send_header("Location", "/published/catalog.json")
                self.end_headers()
                return
            content = {
                "/published/catalog.json": catalog_bytes,
                "/published/collection.json": collection_bytes,
            }.get(self.path)
            if content is None:
                self.send_error(404)
                return
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(content)

        def log_message(self, format: str, *args: object) -> None:
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever)
    thread.start()
    try:
        origin = f"http://127.0.0.1:{server.server_port}"
        catalog = Catalog.open(f"{origin}/entry")

        assert catalog.href == f"{origin}/published/catalog.json"
        assert [collection.id for collection in catalog.collections()] == ["roads"]
    finally:
        server.shutdown()
        thread.join()
        server.server_close()


def test_open_document_returns_the_matching_public_model(tmp_path: Path) -> None:
    documents = [
        ("catalog.json", {"type": "Catalog", "id": "root", "links": []}, Catalog),
        ("collection.json", {"type": "Collection", "id": "roads", "links": []}, Collection),
        ("item.json", {"type": "Feature", "id": "road", "links": []}, Item),
    ]
    for name, data, expected_type in documents:
        path = tmp_path / name
        _write_json(path, data)
        assert isinstance(open_document(path.as_uri()), expected_type)


def test_document_metadata_and_direct_links_are_available(tmp_path: Path) -> None:
    _write_json(
        tmp_path / "catalog.json",
        {
            "type": "Catalog",
            "id": "root",
            "title": "Root",
            "description": None,
            "stac_version": "1.1.0",
            "stac_extensions": ["https://example.test/ext.json"],
            "links": [
                {"rel": "child", "href": "./nested.json"},
                {"rel": "item", "href": "./direct.json"},
            ],
        },
    )
    catalog = open_document(tmp_path / "catalog.json")
    assert isinstance(catalog, Catalog)
    assert catalog.type == "Catalog"
    assert catalog.title == "Root"
    assert catalog.description is None
    assert catalog.stac_version == "1.1.0"
    assert catalog.stac_extensions == ("https://example.test/ext.json",)
    assert [link.original_href for link in catalog.children()] == ["./nested.json"]
    assert [link.original_href for link in catalog.direct_item_links()] == ["./direct.json"]


def test_assets_expose_original_and_resolved_hrefs() -> None:
    collection = Collection(
        {
            "type": "Collection",
            "id": "roads",
            "assets": {"data": {"href": "./data.parquet", "roles": ["data"]}},
        },
        "https://example.test/catalog/collection.json",
    )
    [asset] = list(collection.assets())
    assert asset.original_href == "./data.parquet"
    assert asset.href == "https://example.test/catalog/data.parquet"


def test_read_models_ignore_malformed_optional_metadata() -> None:
    catalog = Catalog(
        {
            "type": 7,
            "title": 7,
            "description": [],
            "stac_version": {},
            "stac_extensions": "not-a-list",
            "links": [
                None,
                {"rel": 7, "href": "ignored.json"},
                {"rel": "child", "href": 7},
                {"rel": "child", "href": "valid.json", "type": 7, "title": []},
            ],
            "assets": {
                "not-an-object": 7,
                "missing-href": {},
                "fallback-type": {
                    "href": "data.bin",
                    "media_type": "application/octet-stream",
                    "roles": "data",
                    "title": 7,
                    "description": [],
                },
            },
        },
        "https://example.test/catalog.json",
    )

    assert catalog.type == ""
    assert catalog.title is None
    assert catalog.description is None
    assert catalog.stac_version is None
    assert catalog.stac_extensions == ()
    [link] = list(catalog.links())
    assert link.media_type is None
    assert link.title is None
    [asset] = list(catalog.assets())
    assert asset.media_type == "application/octet-stream"
    assert asset.roles == ()
    assert asset.title is None
    assert asset.description is None


def test_traversal_stops_at_catalog_cycles(tmp_path: Path) -> None:
    _write_json(
        tmp_path / "catalog.json",
        {
            "type": "Catalog",
            "id": "root",
            "links": [{"rel": "child", "href": "nested.json"}],
        },
    )
    _write_json(
        tmp_path / "nested.json",
        {
            "type": "Catalog",
            "id": "nested",
            "links": [
                {"rel": "child", "href": "catalog.json"},
                {"rel": "item", "href": "item.json"},
            ],
        },
    )

    catalog = Catalog.open(tmp_path)

    assert list(catalog.collections()) == []
    assert [link.original_href for link in catalog.item_links()] == ["item.json"]


def test_unknown_document_type_and_uri_scheme_are_rejected(tmp_path: Path) -> None:
    unknown = tmp_path / "unknown.json"
    _write_json(unknown, {"type": "Unknown", "id": "x"})

    with pytest.raises(ValueError, match="Unsupported STAC document type"):
        open_document(unknown)
    with pytest.raises(ValueError, match="Unsupported URI scheme"):
        Catalog.open("s3://bucket/catalog.json")


def test_validator_accepts_absent_optional_links_and_assets() -> None:
    result = Validator.validate(
        Catalog(
            {
                "type": "Catalog",
                "stac_version": "1.1.0",
                "id": "root",
                "description": "Root",
            },
            "file:///catalog.json",
        )
    )

    assert result.valid


def test_catalog_open_accepts_directory_path(tmp_path: Path) -> None:
    _write_json(
        tmp_path / "catalog.json",
        {
            "type": "Catalog",
            "stac_version": "1.1.0",
            "id": "demo",
            "description": "Demo catalog",
            "links": [],
        },
    )

    catalog = Catalog.open(tmp_path)

    assert catalog.id == "demo"
    assert catalog.href == (tmp_path / "catalog.json").as_uri()


def test_catalog_open_accepts_string_and_file_uri_sources(tmp_path: Path) -> None:
    _write_json(
        tmp_path / "catalog.json",
        {
            "type": "Catalog",
            "stac_version": "1.1.0",
            "id": "demo",
            "description": "Demo catalog",
            "links": [],
        },
    )

    from_string = Catalog.open(str(tmp_path / "catalog.json"))
    from_uri = Catalog.open((tmp_path / "catalog.json").as_uri())

    assert from_string.id == "demo"
    assert from_uri.id == "demo"


@pytest.mark.parametrize(
    "source",
    [r"C:\catalog\catalog.json", r"\\server\share\catalog.json"],
)
def test_windows_paths_are_treated_as_paths_instead_of_uri_schemes(source: str) -> None:
    from portolan.catalog import _source_to_href

    assert _source_to_href(source).startswith("file:")


def test_collection_and_item_open_accept_directory_or_file_sources(tmp_path: Path) -> None:
    _write_json(
        tmp_path / "roads" / "collection.json",
        {
            "type": "Collection",
            "stac_version": "1.1.0",
            "id": "roads",
            "description": "Roads",
            "links": [],
        },
    )
    _write_json(
        tmp_path / "roads" / "road-1" / "item.json",
        {
            "type": "Feature",
            "stac_version": "1.1.0",
            "id": "road-1",
            "collection": "roads",
            "properties": {},
        },
    )

    collection = Collection.open(tmp_path / "roads")
    item = Item.open(tmp_path / "roads" / "road-1" / "item.json")

    assert collection.id == "roads"
    assert collection.href == (tmp_path / "roads" / "collection.json").as_uri()
    assert item.id == "road-1"
    assert item.href == (tmp_path / "roads" / "road-1" / "item.json").as_uri()


def test_catalog_rejects_non_object_json(tmp_path: Path) -> None:
    (tmp_path / "catalog.json").write_text("[]", encoding="utf-8")

    with pytest.raises(TypeError, match="Expected JSON object"):
        Catalog.open(tmp_path / "catalog.json")


def test_documents_ignore_invalid_links_and_assets() -> None:
    data = {
        "type": "Collection",
        "id": "roads",
        "links": [
            "not an object",
            {"rel": "self"},
            {"href": "./missing-rel.json"},
            {"rel": "item", "href": "./item.json", "type": "application/json", "title": "Item"},
        ],
        "assets": {
            "bad": "not an object",
            10: {"href": "./bad-key.parquet"},
            "missing_href": {"type": "application/vnd.apache.parquet"},
            "media_type": {
                "href": "./roads.parquet",
                "media_type": "application/vnd.apache.parquet",
                "roles": ["data", 5],
                "title": "Roads",
                "description": "Road network",
            },
        },
    }

    collection = Collection(data, "https://example.test/catalog/collection.json")
    links = list(collection.links())
    assets = list(collection.assets())

    assert [(link.rel, link.href, link.media_type, link.title) for link in links] == [
        (
            "item",
            "https://example.test/catalog/item.json",
            "application/json",
            "Item",
        )
    ]
    assert len(assets) == 1
    assert assets[0].key == "media_type"
    assert assets[0].media_type == "application/vnd.apache.parquet"
    assert assets[0].roles == ("data",)


def test_is_stac_metadata_identifies_stac_json_documents(tmp_path: Path) -> None:
    catalog_path = tmp_path / "catalog.json"
    style_path = tmp_path / "style.json"
    data_path = tmp_path / "data.parquet"
    broken_path = tmp_path / "broken.json"
    catalog_path.write_text(json.dumps({"type": "Catalog", "id": "demo"}), encoding="utf-8")
    style_path.write_text(json.dumps({"version": 8, "layers": []}), encoding="utf-8")
    data_path.write_bytes(b"PAR1")
    broken_path.write_text("{broken", encoding="utf-8")

    assert is_stac_metadata(catalog_path) is True
    assert is_stac_metadata(style_path) is False
    assert is_stac_metadata(data_path) is False
    assert is_stac_metadata(broken_path) is False


def test_collection_items_only_yields_feature_documents(tmp_path: Path) -> None:
    _write_json(tmp_path / "asset.json", {"type": "Catalog", "id": "not-an-item", "links": []})
    _write_json(
        tmp_path / "item.json",
        {
            "type": "Feature",
            "stac_version": "1.1.0",
            "id": "road-1",
            "collection": "roads",
            "properties": {},
            "links": [],
        },
    )
    collection = Collection(
        {
            "type": "Collection",
            "id": "roads",
            "links": [
                {"rel": "root", "href": "./catalog.json"},
                {"rel": "item", "href": "./asset.json"},
                {"rel": "item", "href": "./item.json"},
            ],
        },
        (tmp_path / "collection.json").as_uri(),
    )

    assert [item.id for item in collection.items()] == ["road-1"]


def test_collection_item_links_descend_organizing_catalogs(tmp_path: Path) -> None:
    _write_json(
        tmp_path / "2024" / "catalog.json",
        {
            "type": "Catalog",
            "stac_version": "1.1.0",
            "id": "roads-2024",
            "description": "Road scenes",
            "links": [
                {"rel": "item", "href": "./road-a.json"},
                {"rel": "child", "href": "./nested/catalog.json"},
            ],
        },
    )
    _write_json(
        tmp_path / "2024" / "nested" / "catalog.json",
        {
            "type": "Catalog",
            "stac_version": "1.1.0",
            "id": "nested",
            "description": "Nested scenes",
            "links": [
                {"rel": "item", "href": "./road-b.json"},
                {"rel": "child", "href": "./other/collection.json"},
            ],
        },
    )
    _write_json(
        tmp_path / "2024" / "nested" / "other" / "collection.json",
        {"type": "Collection", "id": "other", "links": []},
    )
    _write_json(
        tmp_path / "2024" / "road-a.json",
        {"type": "Feature", "id": "road-a", "collection": "roads", "properties": {}},
    )
    _write_json(
        tmp_path / "2024" / "nested" / "road-b.json",
        {"type": "Feature", "id": "road-b", "collection": "roads", "properties": {}},
    )
    collection = Collection(
        {
            "type": "Collection",
            "id": "roads",
            "links": [{"rel": "child", "href": "./2024/catalog.json"}],
        },
        (tmp_path / "collection.json").as_uri(),
    )

    links = list(collection.item_links())

    assert [link.raw["href"] for link in links] == ["./road-a.json", "./road-b.json"]
    assert [link.href for link in links] == [
        (tmp_path / "2024" / "road-a.json").as_uri(),
        (tmp_path / "2024" / "nested" / "road-b.json").as_uri(),
    ]
    assert [item.id for item in collection.items()] == ["road-a", "road-b"]


def test_item_exposes_links_and_asset_metadata() -> None:
    item = Item(
        {
            "type": "Feature",
            "id": "road-1",
            "links": [{"rel": "self", "href": "./item.json"}],
            "assets": {
                "data": {
                    "href": "./data.pmtiles",
                    "title": "Tiles",
                    "description": "Vector tiles",
                }
            },
        },
        "https://example.test/items/road-1.json",
    )

    assert item.href == "https://example.test/items/road-1.json"
    assert item.data["id"] == "road-1"
    assert list(item.links())[0].href == "https://example.test/items/item.json"
    asset = list(item.assets())[0]
    assert asset.title == "Tiles"
    assert asset.description == "Vector tiles"
    assert asset.format is AssetFormat.PMTILES


def test_asset_format_classification_uses_media_type_and_href() -> None:
    collection = {
        "type": "Collection",
        "id": "formats",
        "assets": {
            "parquet": {
                "href": "https://example.test/data",
                "type": "application/vnd.apache.parquet",
            },
            "cog": {"href": "https://example.test/image.tif"},
            "pmtiles": {
                "href": "https://example.test/tiles",
                "type": "application/vnd.pmtiles",
            },
            "unknown": {"href": "https://example.test/readme.txt", "type": "text/plain"},
        },
    }

    formats = {
        asset.key: asset.format
        for asset in Collection(collection, "https://example.test/collection.json").assets()
    }

    assert formats == {
        "parquet": AssetFormat.GEOPARQUET,
        "cog": AssetFormat.COG,
        "pmtiles": AssetFormat.PMTILES,
        "unknown": AssetFormat.UNKNOWN,
    }


def test_validator_reports_missing_required_catalog_fields(tmp_path: Path) -> None:
    _write_json(
        tmp_path / "catalog.json",
        {
            "type": "Catalog",
            "id": "broken",
            "links": [{"href": "./roads/collection.json"}],
        },
    )

    result = Validator.validate(Catalog.open(tmp_path / "catalog.json"))

    assert not result.valid
    assert [(error.code, error.path) for error in result.errors] == [
        ("PTL-STAC-001", "catalog.stac_version"),
        ("PTL-STAC-001", "catalog.description"),
        ("PTL-STAC-002", "catalog.links[0].rel"),
    ]


def test_validator_reports_collection_item_and_asset_errors(tmp_path: Path) -> None:
    _write_json(
        tmp_path / "catalog.json",
        {
            "type": "Catalog",
            "stac_version": "1.1.0",
            "id": "demo",
            "description": "Demo catalog",
            "links": [
                {"rel": "child", "href": "./roads/collection.json", "type": "application/json"}
            ],
        },
    )
    _write_json(
        tmp_path / "roads" / "collection.json",
        {
            "type": "Collection",
            "stac_version": "1.1.0",
            "id": "roads",
            "description": "Roads",
            "extent": {
                "spatial": {"bbox": [[-71.0, -35.0, -70.0, -34.0]]},
                "temporal": {"interval": [[None, None]]},
            },
            "links": [{"rel": "item", "href": "./road-1/road-1.json"}],
            "assets": {"data": {"type": "application/vnd.apache.parquet"}},
        },
    )
    _write_json(
        tmp_path / "roads" / "road-1" / "road-1.json",
        {
            "type": "Feature",
            "stac_version": "1.1.0",
            "id": "road-1",
            "properties": {"datetime": None},
            "links": [],
            "assets": {"data": {"href": "./road-1.parquet"}},
        },
    )

    result = Validator.validate(Catalog.open(tmp_path))

    assert not result.valid
    assert [(error.code, error.path) for error in result.errors] == [
        ("PTL-STAC-001", "collection.roads.license"),
        ("PTL-STAC-003", "collection.roads.assets.data.href"),
        ("PTL-STAC-001", "item.road-1.collection"),
    ]


def test_validator_reports_link_asset_extent_and_properties_shape_errors(
    tmp_path: Path,
) -> None:
    _write_json(
        tmp_path / "catalog.json",
        {
            "type": "Catalog",
            "stac_version": "1.1.0",
            "id": "demo",
            "description": "Demo catalog",
            "links": [{"rel": "child", "href": "./roads/collection.json"}],
        },
    )
    _write_json(
        tmp_path / "roads" / "collection.json",
        {
            "type": "Collection",
            "stac_version": "1.1.0",
            "id": "roads",
            "description": "Roads",
            "license": "CC-BY-4.0",
            "extent": "not an object",
            "links": ["not an object", {"rel": "item", "href": "./road-1/road-1.json"}],
            "assets": ["not an object"],
        },
    )
    _write_json(
        tmp_path / "roads" / "road-1" / "road-1.json",
        {
            "type": "Feature",
            "stac_version": "1.1.0",
            "id": "road-1",
            "collection": "roads",
            "properties": [],
            "links": "not an array",
            "assets": {"bad": "not an object"},
        },
    )

    result = Validator.validate(Catalog.open(tmp_path))

    assert [(error.code, error.path) for error in result.errors] == [
        ("PTL-STAC-001", "collection.roads.extent"),
        ("PTL-STAC-002", "collection.roads.links[0]"),
        ("PTL-STAC-003", "collection.roads.assets"),
        ("PTL-STAC-001", "item.road-1.properties"),
        ("PTL-STAC-002", "item.road-1.links"),
        ("PTL-STAC-003", "item.road-1.assets.bad"),
    ]
