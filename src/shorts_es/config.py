"""Runtime configuration: where local state lives.

Precedence: explicit argument > ``SHORTS_ES_DATA_DIR`` > platform default.
Snapshots and the SQLite ledger are the user's reproducibility substrate, so
they live outside any temporary directory.
"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from pathlib import Path

from . import constants


def default_data_dir() -> Path:
    """Platform-appropriate user data directory."""
    env = os.environ.get(constants.ENV_DATA_DIR)
    if env:
        return Path(env).expanduser()
    if sys.platform == "win32":
        base = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
        return Path(base) / constants.APP_NAME
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / constants.APP_NAME
    base = os.environ.get("XDG_DATA_HOME") or str(Path.home() / ".local" / "share")
    return Path(base) / constants.APP_NAME


@dataclass(frozen=True)
class Config:
    data_dir: Path

    @property
    def db_path(self) -> Path:
        return self.data_dir / constants.DB_FILENAME

    @property
    def snapshots_dir(self) -> Path:
        return self.data_dir / constants.SNAPSHOTS_DIRNAME

    @property
    def manifest_path(self) -> Path:
        return self.data_dir / constants.MANIFEST_FILENAME

    def ensure_dirs(self) -> None:
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.snapshots_dir.mkdir(parents=True, exist_ok=True)

    @classmethod
    def resolve(cls, data_dir: str | Path | None = None) -> Config:
        path = Path(data_dir).expanduser() if data_dir else default_data_dir()
        return cls(data_dir=path)
