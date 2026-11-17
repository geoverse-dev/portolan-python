# Conformance

`portolan-python` implements SDK Read Profile v1.
The profile checks how the SDK reads and navigates Portolan metadata.

Run the profile with:

```bash
make check-conformance
```

The command downloads the pinned `portolan-conformance` release.
It runs the SDK adapter against 25 read behavior cases.
It writes `read-profile-report.json` in the repository root.

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
| Metadata Validation Profile v1 | Not implemented | Test embedded SDK metadata validation. |

Python users can call Rashid directly, so `portolan-python` does not duplicate its normative rules.
Java provides embedded metadata validation because JVM applications cannot call Rashid as a native library.
