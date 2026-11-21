# Scope

`portolan-python` implements Portolan catalog semantics for Python applications.
It is the place for catalog access, STAC traversal, HREF resolution, asset
classification, registry access, and validation.

The public API reads catalogs and authors new catalog graphs in memory.
Authoring produces a storage-independent `WritePlan`; the caller materializes it.
Editing an existing graph is not supported yet.

The library does not process geospatial data files. It can identify a
GeoParquet, COG, or PMTiles asset from metadata, but it does not read the rows,
pixels, or tiles inside that asset.

## Belongs here

- Opening local or remote `catalog.json`, `collection.json`, and item documents.
- Navigating catalogs, collections, items, assets, and links.
- Resolving relative HREFs from the document that declares them.
- Exposing asset media type, roles, and known Portolan asset format.
- Loading registry exports and downloading registry catalog snapshots.
- Validating Portolan and STAC metadata.
- Building new Portolan 0.3.0 catalog graphs in memory.
- Producing deterministic PUT-only plans for metadata and caller-supplied documentation.

## Belongs outside

- Converting source data into GeoParquet or COG.
- Reading raster pixels or GeoParquet rows.
- Creating PMTiles or thumbnails.
- Extracting data from WFS, ArcGIS, or CARTO.
- Publishing catalogs to an application server.
- Running a server process for a catalog.
- Writing a plan to a filesystem, object store, or other destination.

Applications can combine this library with specialized tools. For example,
the external [`geoserver-portolan`](https://github.com/geoverse-dev/geoserver-portolan)
plugin uses the SDK as a catalog reader.
