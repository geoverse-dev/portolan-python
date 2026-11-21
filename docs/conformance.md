# Conformance

`portolan-python` implements SDK Read Profile v1 and Write Profile v1 Round 1.
The read profile checks metadata access and navigation.
The write profile checks in-memory authoring and storage-independent planning.

Run the released conformance pin with:

```bash
make check-conformance
```

The command downloads the pinned `portolan-conformance` release.
Until that release contains Write Profile v1, this target runs the read profile only.
It writes `read-profile-report.json`.

Run the development write profile against a local Conformance checkout:

```bash
make check-conformance-write \
  CONFORMANCE=../portolan-conformance/.venv/bin/portolan-conformance
```

After the next Conformance release, update the pin and use `make check-conformance-all`.

A passing report confirms the tested read behavior.
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
| SDK Write Profile v1, Round 1 | Supported | Author new graphs and produce deterministic PUT-only plans. |
| Metadata Validation Profile v1 | Not implemented | Test embedded SDK metadata validation. |

Python users can call Rashid directly, so `portolan-python` does not duplicate its normative rules.
Java provides embedded metadata validation because JVM applications cannot call Rashid as a native library.
