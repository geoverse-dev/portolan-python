# Portolan Python

A lightweight Python implementation of the Portolan specification.

`portolan-python` provides catalog reading, in-memory authoring, validation, and conformance APIs for Python applications.

The authoring API creates Portolan 0.3.0 metadata and storage-independent write plans.
Applications remain responsible for materializing those plans.

The project intentionally focuses on **Portolan itself**, rather than on geospatial data processing.

It does not aim to replace GDAL, Rasterio, GeoPandas, GeoParquet tooling, tile generators, GIS servers, or other specialized geospatial software.

## Motivation

Portolan defines an opinionated way of organizing and describing cloud-native geospatial data using existing standards and formats such as STAC, GeoParquet, COG, PMTiles, COPC, and Zarr.

Applications integrating with Portolan need a reliable implementation of that contract.

Without a reusable core library, every integration would need to independently implement:

* Portolan catalog semantics;
* STAC traversal;
* collection and asset handling;
* Portolan-specific requirements;
* link and HREF resolution;
* metadata validation;
* conformance rules;
* metadata loading and typed access.

`portolan-python` provides that reusable implementation.

The core design principle is:

> **Portolan defines the contract. Specialized tools implement data processing.**

For example, this library may determine that an asset is a GeoParquet asset and expose its URI and metadata. It does not need to read the GeoParquet rows itself.

Likewise, it may identify a COG asset without becoming a raster processing library.

## Current scope

`portolan-python` is responsible for the Portolan domain model and specification semantics.

Current responsibilities include:

* opening Portolan catalogs;
* reading Portolan/STAC metadata;
* navigating catalogs, collections, items, assets, and links;
* resolving relative and absolute HREFs;
* exposing Portolan extensions and metadata;
* validating Portolan structures;
* checking Portolan conformance;
* exposing asset type and media-type information;
* handling specification versions;
* authoring new catalog graphs in memory;
* producing deterministic PUT-only write plans;
* providing stable Python APIs for applications built on Portolan.

A conceptual API may look like:

```python
from portolan import Catalog

catalog = Catalog.open("https://example.com/catalog.json")

for collection in catalog.collections():
    print(collection.id)

    for asset in collection.assets():
        print(asset.href)
        print(asset.media_type)
        print(asset.roles)
```

Validation should similarly be available programmatically:

```python
from portolan import Catalog, Validator

catalog = Catalog.open("./catalog.json")

result = Validator.validate(catalog)

if not result.valid:
    for error in result.errors:
        print(error)
```

The exact API will evolve during implementation, but it should remain small, explicit, typed, and independent from any CLI.

## Non-goals

This project should **not** become a general-purpose geospatial processing library.

In particular, the core should not be responsible for:

* reading GeoParquet feature data;
* writing GeoParquet datasets;
* converting Shapefile to GeoParquet;
* creating COGs;
* reading raster pixels;
* creating PMTiles;
* processing COPC;
* converting MrSID or ECW;
* extracting data from WFS;
* extracting data from ArcGIS;
* extracting data from CARTO;
* running pygeoapi;
* managing QGIS projects.

Those capabilities belong to specialized libraries, applications, or optional integrations.

Portolan should be opinionated about **what constitutes a conformant Portolan catalog and asset**, not unnecessarily opinionated about **which software must produce or consume those assets**.

## Architecture

```text
                    Portolan Specification
                             │
                             ▼
                      portolan-python
                   ┌────────────────────┐
                   │ Domain model       │
                   │ Catalog access     │
                   │ STAC semantics     │
                   │ Portolan semantics │
                   │ HREF resolution    │
                   │ Validation         │
                   │ Conformance        │
                   └─────────┬──────────┘
                             │
              ┌──────────────┼──────────────┐
              ▼              ▼              ▼
         portolan-cli    integrations    other apps
```

## Relationship with `portolan-cli`

`portolan-cli` should consume this library rather than implement Portolan domain logic itself.

For example:

```text
portolan validate
portolan inspect
portolan registry list
```

should be CLI representations of APIs provided by the Portolan Python ecosystem.

The CLI should remain an interface layer.

## Potential consumers

Python applications and integrations can embed this library without introducing application-specific
dependencies. The external
[`geoserver-portolan`](https://github.com/geoverse-dev/geoserver-portolan)
plugin is one example of a consumer that uses the SDK.

## Relationship with `portolan-java`

`portolan-java` is the Java counterpart of this project.

The two libraries should implement the same **conceptual Portolan contract**, while following the conventions of their respective languages.

They should not necessarily expose identical classes or method signatures.

The Portolan specification remains the source of truth.

```text
                 Portolan Specification
                    /             \
                   /               \
          portolan-python      portolan-java
```

## Design principles

1. Specification first.
2. Small and stable public API.
3. No CLI dependency.
4. No application-server dependency.
5. No mandatory geospatial processing stack.
6. Specialized formats are represented, not reimplemented.
7. External applications should not need to reimplement Portolan semantics.
8. The library should be suitable as a dependency of long-lived applications.

## Next steps

The authoring API creates and edits graphs without storage access.
Deletion planning requires an explicit snapshot of previously managed metadata keys.
Storage materialization remains application-owned.
Write Profile v1.1 also covers complete structural links and copy-on-write
documentation changes.

## Local documentation

- [Scope](docs/scope.md) defines what belongs in this core library.
- [Authoring](docs/authoring.md) shows in-memory graphs and storage-independent plans.
- [Examples](docs/examples.md) shows basic API usage.
- [Development](docs/development.md) lists setup, test, and build commands.
- [Distribution](docs/distribution.md) explains releases, `pip`, and PyPI publishing.
- [Conformance](docs/conformance.md) explains SDK conformance and catalog validation.

## Conformance checks

Install the pinned `portolan-conformance` revision from the CI workflow.
Then run the SDK adapter against the released read and write profiles:

```bash
make check-conformance
```

The target writes `read-profile-report.json` and `write-profile-report.json`.
Use `make check-conformance-write` to run only Write Profile v1.1.
It does not validate full catalog conformance.

See [Conformance](docs/conformance.md) for the supported profile and Rashid integration.

---
