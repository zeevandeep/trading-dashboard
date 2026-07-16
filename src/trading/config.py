"""Configuration loading — environment variables and strategy YAML configs."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml
from dotenv import load_dotenv

# Project root resolves from this file's location
PROJECT_ROOT = Path(__file__).resolve().parents[2]

# Standard directories
DATA_DIR = PROJECT_ROOT / "data"
CACHE_DIR = DATA_DIR / "cache"
UNIVERSE_DIR = DATA_DIR / "universe"
CONFIGS_DIR = PROJECT_ROOT / "configs"
OUTPUTS_DIR = PROJECT_ROOT / "outputs"
LOGS_DIR = PROJECT_ROOT / "logs"

# Load .env on import
load_dotenv(PROJECT_ROOT / ".env")


@dataclass
class Secrets:
    """Runtime secrets loaded from environment. Never logged, never persisted."""

    kite_api_key: str = ""
    kite_api_secret: str = ""
    angel_api_key: str = ""
    angel_client_id: str = ""
    angel_password: str = ""
    angel_totp_secret: str = ""
    proxy_url: str = ""
    proxy_api_key: str = ""

    @classmethod
    def from_env(cls) -> "Secrets":
        return cls(
            kite_api_key=os.getenv("KITE_API_KEY", ""),
            kite_api_secret=os.getenv("KITE_API_SECRET", ""),
            angel_api_key=os.getenv("ANGEL_API_KEY", ""),
            angel_client_id=os.getenv("ANGEL_CLIENT_ID", ""),
            angel_password=os.getenv("ANGEL_PASSWORD", ""),
            angel_totp_secret=os.getenv("ANGEL_TOTP_SECRET", ""),
            proxy_url=os.getenv("PROXY_URL", ""),
            proxy_api_key=os.getenv("PROXY_API_KEY", ""),
        )

    def __repr__(self) -> str:
        # Redact secrets in any string representation
        def redact(s: str) -> str:
            if not s:
                return "<empty>"
            return f"{s[:4]}...{s[-2:]}" if len(s) > 6 else "***"

        return (
            f"Secrets(kite_api_key={redact(self.kite_api_key)}, "
            f"angel_client_id={redact(self.angel_client_id)})"
        )


def get_env() -> str:
    """Current trading environment: research | paper | live."""
    return os.getenv("TRADING_ENV", "research")


def load_strategy_config(config_path: str | Path) -> dict[str, Any]:
    """Load a strategy YAML config.

    Accepts any of:
      - absolute path: /full/path/to/config.yaml
      - cwd-relative: configs/smallcap_momentum_v1.yaml (when run from project root)
      - configs-relative: smallcap_momentum_v1.yaml (just the filename)
    """
    path = Path(config_path)
    candidates: list[Path] = [path]
    if not path.is_absolute():
        # Treat as configs-relative (just a filename)
        candidates.append(CONFIGS_DIR / path.name)
        # Or treat as project-root-relative
        candidates.append(PROJECT_ROOT / path)

    for candidate in candidates:
        if candidate.exists():
            with candidate.open("r") as f:
                return yaml.safe_load(f)

    tried = "\n  ".join(str(c) for c in candidates)
    raise FileNotFoundError(f"Strategy config not found. Tried:\n  {tried}")


def ensure_dirs() -> None:
    """Create runtime directories if they don't exist."""
    for d in (CACHE_DIR, OUTPUTS_DIR, LOGS_DIR):
        d.mkdir(parents=True, exist_ok=True)
