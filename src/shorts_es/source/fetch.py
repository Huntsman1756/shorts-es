"""HTTP fetch of the CNMV workbook with full provenance metadata."""

from __future__ import annotations

import time
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import httpx

from .. import constants
from ..exceptions import SourceUnavailableError

HTTP_TIMEOUT_S = 60.0
USER_AGENT = f"{constants.APP_NAME}/0.1 (+{constants.SOURCE_PAGE_URL})"


@dataclass(frozen=True)
class FetchResult:
    content: bytes
    retrieved_at: datetime
    source_url: str
    http_status: int | None
    content_type: str | None
    content_length: int | None
    etag: str | None
    last_modified: str | None
    local_file: str | None = None


FETCH_RETRIES = 3
RETRY_BACKOFF_S = 5.0


def fetch_source(url: str = constants.SOURCE_URL) -> FetchResult:
    """Download the source workbook. Raises SourceUnavailableError on failure.

    Retries a few times with backoff: the CNMV endpoint occasionally drops
    connections without a response.
    """
    retrieved_at = datetime.now(UTC)
    last_exc: httpx.HTTPError | None = None
    for attempt in range(FETCH_RETRIES):
        try:
            with httpx.Client(
                timeout=HTTP_TIMEOUT_S,
                follow_redirects=True,
                headers={"User-Agent": USER_AGENT, "Accept": "*/*"},
            ) as client:
                resp = client.get(url)
                resp.raise_for_status()
            break
        except httpx.HTTPError as exc:
            last_exc = exc
            if attempt < FETCH_RETRIES - 1:
                time.sleep(RETRY_BACKOFF_S * (attempt + 1))
    else:
        raise SourceUnavailableError(f"{url}: {last_exc}") from last_exc

    headers = resp.headers
    return FetchResult(
        content=resp.content,
        retrieved_at=retrieved_at,
        source_url=url,
        http_status=resp.status_code,
        content_type=headers.get("content-type"),
        content_length=len(resp.content),
        etag=headers.get("etag"),
        last_modified=headers.get("last-modified"),
    )


def fetch_local(path: str | Path, source_url: str = constants.SOURCE_URL) -> FetchResult:
    """Ingest a workbook from a local file (offline / replay mode).

    ``retrieved_at`` is still recorded: it is when *we* ingested the bytes,
    not when CNMV published them.
    """
    p = Path(path)
    if not p.is_file():
        raise SourceUnavailableError(f"local file not found: {p}")
    content = p.read_bytes()
    return FetchResult(
        content=content,
        retrieved_at=datetime.now(UTC),
        source_url=source_url,
        http_status=None,
        content_type="application/vnd.ms-excel",
        content_length=len(content),
        etag=None,
        last_modified=None,
        local_file=str(p),
    )
