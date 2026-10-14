from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "core"))

from execcon_v2.platform_probe import collect_platform_snapshot
from execcon_v2.safe_json import write_public_json
from execcon_v2.settings import load_settings


def main() -> int:
    parser = argparse.ArgumentParser(description="Collect a no-model EvoHarness platform snapshot.")
    parser.add_argument("--output", type=Path, default=ROOT / "manifests" / "platform_snapshot.json")
    args = parser.parse_args()

    settings = load_settings(require_model_key=False)
    from simple_agentic_evals import EvalClient

    with EvalClient(
        base_url=settings.eval_service_url,
        api_key=settings.eval_service_api_key,
        timeout=300.0,
    ) as client:
        snapshot = collect_platform_snapshot(
            client,
            settings.dataset,
            settings.benchmark,
            stages=[1, 2, 3, 4, 5, 6],
        )
    snapshot["experiment"] = settings.public_manifest()
    write_public_json(args.output, snapshot)
    print(args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
