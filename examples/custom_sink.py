"""Application-owned materialization of a Portolan WritePlan."""

from __future__ import annotations

from dataclasses import dataclass, field

from portolan import CatalogBuilder, WritePlan, WritePlanner


@dataclass
class MemorySink:
    objects: dict[str, bytes] = field(default_factory=dict)

    def put(self, key: str, content: bytes) -> None:
        self.objects[key] = content

    def delete(self, key: str) -> None:
        self.objects.pop(key, None)


def apply_plan(plan: WritePlan, sink: MemorySink) -> None:
    for operation in plan.operations:
        if operation.kind == "put":
            sink.put(operation.key, operation.content)
        else:
            sink.delete(operation.key)


def main() -> None:
    graph = (
        CatalogBuilder(id="demo", spec_version="0.3.0")
        .title("Demo")
        .description("Application-managed publication.")
        .build()
    )
    plan = WritePlanner().plan(graph)
    sink = MemorySink()
    apply_plan(plan, sink)
    assert "catalog.json" in sink.objects


if __name__ == "__main__":
    main()
