# Conformance

`portolan-python` implements SDK Read Profile v1 and Write Profile v1.1.
The read profile checks metadata access and navigation.
The write profile checks in-memory authoring and storage-independent planning.

The development read profile distinguishes direct item links from recursive collection items.
It also checks HTTP redirects and strict preservation of JSON scalar types.

Run the released conformance pin with:

```bash
make check-conformance
```

The command downloads the pinned `portolan-conformance` release.
It runs both profiles and writes `read-profile-report.json` and
`write-profile-report.json`.

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
| SDK Write Profile v1.1 | Supported | Author and edit graphs, documentation, and deterministic PUT/DELETE plans. |
| Metadata Validation Profile v1 | Not implemented | Test embedded SDK metadata validation. |

Python users can call Rashid directly, so `portolan-python` does not duplicate its normative rules.
Java provides embedded metadata validation because JVM applications cannot call Rashid as a native library.
