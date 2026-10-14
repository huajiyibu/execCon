from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Iterable


def _task_set(client: Any, dataset: str, benchmark: str, version: int | str) -> dict[str, Any]:
    task_ids = list(client.task_ids(dataset, benchmark, version, split="test"))
    return {"count": len(task_ids), "task_ids": task_ids}


def collect_platform_snapshot(
    client: Any,
    dataset: str,
    benchmark: str,
    *,
    stages: Iterable[int],
) -> dict[str, Any]:
    stages = list(stages)
    task_sets: dict[str, Any] = {}
    for version in [*stages, "full"]:
        label = str(version)
        try:
            task_sets[label] = {"status": "ok", **_task_set(client, dataset, benchmark, version)}
        except Exception as exc:
            task_sets[label] = {
                "status": "error",
                "error_type": type(exc).__name__,
                "error": str(exc),
            }

    anchor_ids = task_sets.get(str(stages[0]), {}).get("task_ids") if stages else None
    anchor_task = anchor_ids[0] if anchor_ids else None
    resources: dict[str, Any] = {}
    for stage in stages:
        label = f"h{stage}"
        if not anchor_task:
            resources[label] = {"status": "not_run", "error": "no stage-1 anchor task"}
            continue
        try:
            resource = client.resources(
                dataset,
                benchmark,
                stages[0],
                task_id=anchor_task,
                split="test",
                mode="accumulative",
                include_content=False,
                at_stage=stage,
            )
            resources[label] = {
                "status": "ok",
                "mode": resource.get("mode"),
                "stage": resource.get("stage"),
                "count": resource.get("count"),
                "names": resource.get("names") or [],
            }
        except Exception as exc:
            resources[label] = {
                "status": "error",
                "error_type": type(exc).__name__,
                "error": str(exc),
            }

    if anchor_task:
        try:
            full = client.resources(
                dataset,
                benchmark,
                "full",
                task_id=anchor_task,
                split="test",
                mode="accumulative",
                include_content=False,
            )
            resources["full"] = {
                "status": "ok",
                "mode": full.get("mode"),
                "stage": full.get("stage"),
                "count": full.get("count"),
                "names": full.get("names") or [],
            }
        except Exception as exc:
            resources["full"] = {
                "status": "error",
                "error_type": type(exc).__name__,
                "error": str(exc),
            }

    catalog = client.benchmarks()
    target_catalog = None
    for dataset_row in catalog.get("datasets", []):
        if dataset_row.get("dataset") != dataset:
            continue
        for benchmark_row in dataset_row.get("benchmarks", []):
            if benchmark_row.get("benchmark") == benchmark:
                target_catalog = {"dataset": dataset, "benchmark": benchmark_row}
                break

    return {
        "schema_version": 1,
        "captured_at": datetime.now(timezone.utc).isoformat(),
        "dataset": dataset,
        "benchmark": benchmark,
        "health": client.health(),
        "target_catalog": target_catalog,
        "task_sets": task_sets,
        "resources": resources,
        "claims": {
            "task_manifest_label": f"service-current-{task_sets.get('full', {}).get('count', 'unknown')}",
            "paper_63_equivalence_confirmed": False,
        },
    }
