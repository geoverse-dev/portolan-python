# Conformance

`portolan-python` implements four behavioral profiles from `portolan-conformance` `v0.4.0`.
The read profile checks metadata access and navigation.
The resource resolution profile checks deterministic HTTP and URI behavior.
The compatibility profile checks Portolan 0.2.0 and 0.3.0 reads.
The write profile checks in-memory authoring and storage-independent planning.

The development read profile distinguishes direct item links from recursive collection items.
It also checks HTTP redirects and strict preservation of JSON scalar types.

Run the released conformance pin with:

```bash
make check-conformance
```

The command downloads the pinned `portolan-conformance` release.
It runs all four profiles and writes one JSON report for each profile.

Run only the write profile against a local Conformance checkout:

```bash
make check-conformance-write \
  CONFORMANCE=../portolan-conformance/.venv/bin/portolan-conformance
```

A passing report confirms the tested SDK behavior.
It does not confirm that a catalog conforms to the Portolan specification.

## Validate a catalog

Use [`rashid`](https://github.com/portolan-sdi/rashid) for normative catalog validation.
Rashid checks metadata, structure, extensions, asset bytes, and hosting behavior.

Python applications can use both libraries for separate tasks:

```python
from portolan import open_document
from rashid import validate

document = open_document("https://example.test/catalog.json")
report = validate("https://example.test/catalog.json")

if report.errors:
    for finding in report.errors:
        print(finding.message)
```

`open_document()` reads the metadata through `portolan-python`.
`validate()` checks the catalog through Rashid.

## Supported profiles

| Profile | Status | Purpose |
|---|---|---|
| SDK Read Profile v1 | Supported | Read and navigate STAC metadata consistently. |
| Resource Resolution Profile v1 | Supported | Resolve local HTTP resources and stable transport errors. |
| Compatibility Profile v1 | Supported | Preserve read behavior for Portolan 0.2.0 and 0.3.0. |
| SDK Write Profile v1.1 | Supported | Author and edit graphs, documentation, and deterministic PUT/DELETE plans. |
| Metadata Validation Profile v1 | Not implemented | Test embedded SDK metadata validation. |

Python users can call Rashid directly, so `portolan-python` does not duplicate its normative rules.
Java provides embedded metadata validation because JVM applications cannot call Rashid as a native library.
