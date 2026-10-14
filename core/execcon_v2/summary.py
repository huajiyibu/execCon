from __future__ import annotations

from typing import Any


def summarize_cells(cells: list[dict[str, Any]]) -> dict[str, Any]:
    graded = [c for c in cells if c.get("status") == "graded"]
    infrastructure = [c for c in cells if c.get("status") == "infrastructure_error"]
    by_condition: dict[str, dict[str, dict[str, Any]]] = {}
    for cell in graded:
        by_condition.setdefault(cell["condition"], {})[cell["treatment"]] = cell
    paired = {}
    for condition, treatments in by_condition.items():
        if "E0" in treatments and "E1" in treatments:
            paired[condition] = {
                "pass_delta_e1_minus_e0": int(bool(treatments["E1"]["pass"])) - int(bool(treatments["E0"]["pass"])),
                "score_delta_e1_minus_e0": float(treatments["E1"]["score"]) - float(treatments["E0"]["score"]),
            }
        if "E1" in treatments and "E2" in treatments:
            paired.setdefault(condition, {})["score_delta_e1_minus_e2"] = float(treatments["E1"]["score"]) - float(treatments["E2"]["score"])
    return {
        "schema_version": 1,
        "n_cells": len(cells),
        "n_graded": len(graded),
        "n_infrastructure": len(infrastructure),
        "mean_score": sum(float(c["score"]) for c in graded) / len(graded) if graded else None,
        "pass_rate": sum(bool(c["pass"]) for c in graded) / len(graded) if graded else None,
        "paired": paired,
    }
