from __future__ import annotations

import threading
from collections import defaultdict
from datetime import UTC, datetime

from dev_workspace_mcp.models.services import GetLogsResponse, LogLine


class ServiceLogStore:
    """Accumulates in-memory log buffers per service."""

    def __init__(self) -> None:
        self._lines: dict[str, list[LogLine]] = defaultdict(list)
        self._lock = threading.Lock()

    def append(self, key: str, stream: str, text: str) -> None:
        """Append normalized log text for a service."""

        if not text:
            return
        with self._lock:
            bucket = self._lines[key]
            for raw_line in text.splitlines() or [text]:
                bucket.append(
                    LogLine(
                        message=raw_line,
                        stream=stream,
                        line_number=len(bucket),
                        timestamp=datetime.now(UTC),
                    )
                )

    def slice(self, key: str, *, offset: int = 0, limit: int = 200) -> GetLogsResponse:
        with self._lock:
            lines = self._lines.get(key, [])
            selected = lines[offset : offset + limit]
            next_offset = offset + limit if offset + limit < len(lines) else None
            return GetLogsResponse(
                service_name=key.split(":", 1)[1] if ":" in key else key,
                lines=[line.model_copy(deep=True) for line in selected],
                next_offset=next_offset,
                truncated=next_offset is not None,
            )


__all__ = ["ServiceLogStore"]
