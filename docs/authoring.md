# Author catalogs in memory

The authoring API builds Portolan 0.3.0 metadata without a storage destination.
It returns a deterministic `WritePlan`; your application decides how to store it.

```python
from portolan import CatalogBuilder, WritePlanner

graph = (
    CatalogBuilder(id="nepal", spec_version="0.3.0")
    .title("Nepal data")
    .description("Climate and geographic data.")
    .build()
)

plan = WritePlanner().plan(graph)
for operation in plan.operations:
    print(operation.kind, operation.key, operation.content)
```

`CatalogGraph.from_dict()` imports an existing STAC dictionary graph.
It preserves unknown document fields and existing asset references.
The planner adds required structural links and the pinned Portolan 0.3.0 schema URI.

New graph plans contain PUT operations only.
`CatalogEditor` applies copy-on-write field, document, and asset changes.
When the caller supplies `prior_managed_keys`, the planner can add DELETE operations
for metadata that the caller explicitly identifies as previously managed.
It never infers deletions by scanning storage and never deletes asset data implicitly.

Plans never open a filesystem path, contact object storage, or inspect asset bytes.
The caller must supply README and AGENTS content when those files belong in the plan.

Planner preflight checks required metadata, managed paths, and graph ownership.
These checks protect plan construction but do not prove normative conformance.
Use `rashid` after materialization to validate the complete catalog and its assets.

Storage sinks and automatic storage reconciliation remain outside the SDK.

The [custom sink example](../examples/custom_sink.py) applies a plan through
application-owned `put` and `delete` methods. The example uses memory and adds no dependency.
