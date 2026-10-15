from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path


class SettingsError(ValueError):
    pass


def _load_dotenv() -> None:
    """Load a local .env without overriding variables already in the process."""
    candidates = [Path.cwd() / ".env", Path(__file__).resolve().parents[2] / ".env"]
    for path in candidates:
        if not path.is_file():
            continue
        for raw in path.read_text(encoding="utf-8").splitlines():
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            key, value = key.strip(), value.strip().strip("'\"")
            if key and key not in os.environ:
                os.environ[key] = value
        break


@dataclass(frozen=True)
class Settings:
    dmxapi_api_key: str = field(repr=False)
    eval_service_api_key: str = field(repr=False)
    dmxapi_base_url: str = "https://www.dmxapi.cn/v1"
    eval_service_url: str = ""
    model: str = "gpt-5.6-luna"
    dataset: str = "evovling_agents"
    benchmark: str = "ale"

    def public_manifest(self) -> dict[str, str]:
        return {
            "dmxapi_base_url": self.dmxapi_base_url,
            "eval_service_url": self.eval_service_url,
            "model": self.model,
            "dataset": self.dataset,
            "benchmark": self.benchmark,
        }


def load_settings(*, require_model_key: bool = True) -> Settings:
    _load_dotenv()
    dmx = os.environ.get("DMXAPI_API_KEY", "")
    evaluation = os.environ.get("EVAL_SERVICE_API_KEY", "")
    service_url = os.environ.get("EVAL_SERVICE_URL", "")
    missing = []
    if require_model_key and not dmx:
        missing.append("DMXAPI_API_KEY")
    if not evaluation:
        missing.append("EVAL_SERVICE_API_KEY")
    if not service_url:
        missing.append("EVAL_SERVICE_URL")
    if missing:
        raise SettingsError(f"missing required environment variables: {', '.join(missing)}")
    return Settings(
        dmxapi_api_key=dmx,
        eval_service_api_key=evaluation,
        dmxapi_base_url=os.environ.get("DMXAPI_BASE_URL", "https://www.dmxapi.cn/v1"),
        eval_service_url=service_url,
        model=os.environ.get("DMXAPI_MODEL", "gpt-5.6-luna"),
    )
