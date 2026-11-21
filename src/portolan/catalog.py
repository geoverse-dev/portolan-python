"""Domain model and catalog traversal for Portolan/STAC catalogs."""

from __future__ import annotations

import json
from collections.abc import Iterator
from dataclasses import dataclass
from enum import Enum
from pathlib import Path, PureWindowsPath
from typing import Any
from urllib.parse import unquote, urljoin, urlparse
from urllib.request import Request, urlopen

JsonObject = dict[str, Any]
STAC_DOCUMENT_TYPES = frozenset({"Catalog", "Collection", "Feature"})


class AssetFormat(Enum):
    """Known cloud-native asset formats represented by Portolan catalogs."""

    GEOPARQUET = "GeoParquet"
    COG = "COG"
    PMTILES = "PMTiles"
    UNKNOWN = "Unknown"


@dataclass(frozen=True)
class Link:
    """A STAC link with its HREF resolved against the containing document."""

    rel: str
    href: str
    media_type: str | None
    title: str | None
    raw: JsonObject

    @property
    def original_href(self) -> str:
        """Return the HREF exactly as authored in the containing document."""
        value = self.raw.get("href")
        return value if isinstance(value, str) else ""


@dataclass(frozen=True)
class Asset:
    """A STAC asset with Portolan-friendly accessors."""

    key: str
    href: str
    media_type: str | None
    roles: tuple[str, ...]
    title: str | None
    description: str | None
    raw: JsonObject

    @property
    def original_href(self) -> str:
        """Return the HREF exactly as authored in the containing document."""
        value = self.raw.get("href")
        return value if isinstance(value, str) else ""

    @property
    def format(self) -> AssetFormat:
        """Return the known Portolan asset format, without reading the asset bytes."""
        media_type = self.media_type or ""
        href_path = urlparse(self.href).path.lower()
        if media_type == "application/vnd.apache.parquet" or href_path.endswith(".parquet"):
            return AssetFormat.GEOPARQUET
        if (
            media_type == "image/tiff; application=geotiff; profile=cloud-optimized"
            or href_path.endswith((".tif", ".tiff"))
        ):
            return AssetFormat.COG
        if media_type == "application/vnd.pmtiles" or href_path.endswith(".pmtiles"):
            return AssetFormat.PMTILES
        return AssetFormat.UNKNOWN


class StacDocument:
    """Common read-only access to a loaded STAC metadata document."""

    def __init__(self, data: JsonObject, href: str) -> None:
        self._data = data
        self._href = href

    @property
    def id(self) -> str:
        return str(self._data.get("id", ""))

    @property
    def type(self) -> str:
        value = self._data.get("type")
        return value if isinstance(value, str) else ""

    @property
    def title(self) -> str | None:
        value = self._data.get("title")
        return value if isinstance(value, str) else None

    @property
    def description(self) -> str | None:
        value = self._data.get("description")
        return value if isinstance(value, str) else None

    @property
    def stac_version(self) -> str | None:
        value = self._data.get("stac_version")
        return value if isinstance(value, str) else None

    @property
    def stac_extensions(self) -> tuple[str, ...]:
        value = self._data.get("stac_extensions")
        if not isinstance(value, list):
            return ()
        return tuple(extension for extension in value if isinstance(extension, str))

    @property
    def href(self) -> str:
        return self._href

    @property
    def data(self) -> JsonObject:
        return dict(self._data)

    def links(self) -> Iterator[Link]:
        yield from _links(self._data, self._href)

    def assets(self) -> Iterator[Asset]:
        """Yield metadata for assets without reading their bytes."""
        yield from _assets(self._data, self._href)

    def children(self) -> Iterator[Link]:
        """Yield direct STAC child links without traversing their targets."""
        yield from (link for link in self.links() if link.rel == "child")

    def direct_item_links(self) -> Iterator[Link]:
        """Yield direct STAC item links without traversing child catalogs."""
        yield from (link for link in self.links() if link.rel == "item")


class Catalog(StacDocument):
    """A loaded Portolan catalog root."""

    @classmethod
    def open(cls, source: str | Path) -> Catalog:
        """Open a local or remote Portolan catalog document."""
        href = _source_to_href(source)
        data, href = _read_json_document(href)
        return cls(data, href)

    def collections(self) -> Iterator[Collection]:
        """Yield child collections, including collections below child catalogs."""
        yield from _collections_from_catalog(self._data, self._href, set())

    def item_links(self) -> Iterator[Link]:
        """Yield item links owned by this catalog subtree."""
        yield from _item_links_from_document(self._data, self._href, set())


class Collection(StacDocument):
    """A loaded STAC Collection within a Portolan catalog."""

    @classmethod
    def open(cls, source: str | Path) -> Collection:
        """Open a local or remote STAC Collection document."""
        href = _source_to_href(source, default_document="collection.json")
        data, href = _read_json_document(href)
        return cls(data, href)

    def items(self) -> Iterator[Item]:
        """Yield linked items from this collection."""
        for link in self.item_links():
            data, item_href = _read_json_document(link.href)
            if data.get("type") == "Feature":
                yield Item(data, item_href)

    def item_links(self) -> Iterator[Link]:
        """Yield item links owned by this collection.

        A collection can group items behind child catalogs. Those items still
        belong to the collection, so traversal follows child catalogs and stops
        at child collections.
        """
        yield from _item_links_from_document(self._data, self._href, set())


class Item(StacDocument):
    """A loaded STAC Item."""

    @classmethod
    def open(cls, source: str | Path) -> Item:
        """Open a local or remote STAC Item document."""
        href = _source_to_href(source, default_document="item.json")
        data, href = _read_json_document(href)
        return cls(data, href)

def open_document(source: str | Path) -> Catalog | Collection | Item:
    """Open any supported STAC metadata document using its declared type."""
    href = _source_to_href(source)
    data, href = _read_json_document(href)
    document_type = data.get("type")
    if document_type == "Catalog":
        return Catalog(data, href)
    if document_type == "Collection":
        return Collection(data, href)
    if document_type == "Feature":
        return Item(data, href)
    raise ValueError(f"Unsupported STAC document type: {document_type!r}")


def is_stac_metadata(source: str | Path) -> bool:
    """Return whether ``source`` is a STAC Catalog, Collection, or Item document."""
    if isinstance(source, Path) and source.suffix.lower() != ".json":
        return False
    try:
        data = _read_json_href(_source_to_href(source, default_document="catalog.json"))
    except (OSError, TypeError, ValueError, json.JSONDecodeError):
        return False
    return data.get("type") in STAC_DOCUMENT_TYPES


def _collections_from_catalog(
    data: JsonObject, href: str, visited: set[str]
) -> Iterator[Collection]:
    if href in visited:
        return
    visited.add(href)
    for link in _links(data, href):
        if link.rel != "child":
            continue
        child, child_href = _read_json_document(link.href)
        child_type = child.get("type")
        if child_type == "Collection":
            yield Collection(child, child_href)
        elif child_type == "Catalog":
            yield from _collections_from_catalog(child, child_href, visited)


def _item_links_from_document(data: JsonObject, href: str, visited: set[str]) -> Iterator[Link]:
    if href in visited:
        return
    visited.add(href)
    for link in _links(data, href):
        if link.rel == "item":
            yield link
        elif link.rel == "child":
            child, child_href = _read_json_document(link.href)
            if child.get("type") == "Catalog":
                yield from _item_links_from_document(child, child_href, visited)


def _links(data: JsonObject, document_href: str) -> Iterator[Link]:
    links = data.get("links")
    if not isinstance(links, list):
        return
    for raw_link in links:
        if not isinstance(raw_link, dict):
            continue
        rel = raw_link.get("rel")
        href = raw_link.get("href")
        if not isinstance(rel, str) or not isinstance(href, str):
            continue
        media_type = raw_link.get("type")
        title = raw_link.get("title")
        yield Link(
            rel=rel,
            href=_resolve_href(document_href, href),
            media_type=media_type if isinstance(media_type, str) else None,
            title=title if isinstance(title, str) else None,
            raw=dict(raw_link),
        )


def _assets(data: JsonObject, document_href: str) -> Iterator[Asset]:
    assets = data.get("assets")
    if not isinstance(assets, dict):
        return
    for key, raw_asset in assets.items():
        if not isinstance(key, str) or not isinstance(raw_asset, dict):
            continue
        href = raw_asset.get("href")
        if not isinstance(href, str):
            continue
        media_type = raw_asset.get("type") or raw_asset.get("media_type")
        roles = raw_asset.get("roles")
        title = raw_asset.get("title")
        description = raw_asset.get("description")
        yield Asset(
            key=key,
            href=_resolve_href(document_href, href),
            media_type=media_type if isinstance(media_type, str) else None,
            roles=tuple(role for role in roles if isinstance(role, str))
            if isinstance(roles, list)
            else (),
            title=title if isinstance(title, str) else None,
            description=description if isinstance(description, str) else None,
            raw=dict(raw_asset),
        )


def _source_to_href(source: str | Path, *, default_document: str = "catalog.json") -> str:
    if isinstance(source, Path):
        path = source
    else:
        if PureWindowsPath(source).is_absolute():
            path = Path(source)
        else:
            parsed = urlparse(source)
            if parsed.scheme in {"http", "https", "file"}:
                return source
            if parsed.scheme:
                raise ValueError(f"Unsupported URI scheme: {parsed.scheme}")
            path = Path(source)
    if path.is_dir():
        path = path / default_document
    return path.resolve().as_uri()


def _read_json_href(href: str) -> JsonObject:
    return _read_json_document(href)[0]


def _read_json_document(href: str) -> tuple[JsonObject, str]:
    parsed = urlparse(href)
    if parsed.scheme in {"http", "https"}:
        request = Request(href, headers={"User-Agent": "portolan-python"})
        with urlopen(request, timeout=30) as response:
            data = json.loads(response.read().decode("utf-8"))
            final_href = response.geturl()
    elif parsed.scheme == "file":
        path = Path(unquote(parsed.path))
        data = json.loads(path.read_text(encoding="utf-8"))
        final_href = href
    else:
        data = json.loads(Path(href).read_text(encoding="utf-8"))
        final_href = href
    if not isinstance(data, dict):
        raise TypeError(f"Expected JSON object from {href}")
    return data, final_href


def _resolve_href(document_href: str, href: str) -> str:
    return urljoin(document_href, href)
