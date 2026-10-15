from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class StageConfig:
    name: str
    cohort: int
    harness: int
    specialists: tuple[str, ...]
    task_id: str
    resource_mode: str = "accumulative"


TASK_ID = "business_finance/american_option_pricing_ls"

STAGES = {
    "h1": StageConfig("h1", 1, 1, ("numerics_stats", "runtime_base"), TASK_ID),
    "h2": StageConfig(
        "h2", 2, 2,
        ("domain_simulation", "machine_learning", "numerics_stats", "runtime_base", "tabular_data"),
        TASK_ID,
    ),
    "h3": StageConfig(
        "h3", 3, 3,
        ("browser", "creative_3d", "domain_simulation", "imaging", "machine_learning", "numerics_stats", "runtime_base", "tabular_data"),
        TASK_ID,
    ),
}


def get_stage(name: str) -> StageConfig:
    try:
        return STAGES[name]
    except KeyError as exc:
        raise ValueError(f"unsupported stage: {name}; choose h1, h2, or h3") from exc
