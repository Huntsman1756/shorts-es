"""Immutable snapshot storage.

Raw bytes are content-addressed: ``snapshots/<sha256>.xls``. The same content
is never stored twice and historical snapshots are never overwritten.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from ..config import Config
from .fetch import FetchResult


@dataclass(frozen=True)
class StoredSnapshot:
    sha256: str
    raw_path: Path
    retrieved_at: datetime
    already_existed: bool
    fetch: FetchResult


def sha256_bytes(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def snapshot_path(config: Config, sha256: str) -> Path:
    return config.snapshots_dir / f"{sha256}.xls"


def store_snapshot(config: Config, fetch: FetchResult) -> StoredSnapshot:
    """Persist raw bytes if new. Returns the stored snapshot descriptor."""
    config.ensure_dirs()
    digest = sha256_bytes(fetch.content)
    path = snapshot_path(config, digest)
    existed = path.exists()
    if not existed:
        tmp = path.with_suffix(".tmp")
        tmp.write_bytes(fetch.content)
        if sha256_bytes(tmp.read_bytes()) != digest:  # defensive: write integrity
            tmp.unlink(missing_ok=True)
            raise OSError("snapshot write failed integrity check")
        tmp.replace(path)
    return StoredSnapshot(
        sha256=digest,
        raw_path=path,
        retrieved_at=fetch.retrieved_at,
        already_existed=existed,
        fetch=fetch,
    )


def append_manifest(config: Config, entry: dict) -> None:
    """Append a snapshot descriptor line to the local JSONL manifest."""
    config.ensure_dirs()
    with config.manifest_path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(entry, ensure_ascii=False, sort_keys=True) + "\n")


def read_snapshot_bytes(config: Config, sha256: str) -> bytes:
    return snapshot_path(config, sha256).read_bytes()


def resolve_snapshot_prefix(config: Config, prefix: str) -> str | None:
    """Resolve an unambiguous sha256 prefix to a full digest."""
    matches = sorted(p.stem for p in config.snapshots_dir.glob(f"{prefix}*.xls"))
    if len(matches) == 1:
        return matches[0]
    return None
