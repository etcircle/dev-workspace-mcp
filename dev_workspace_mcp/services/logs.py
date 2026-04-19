from __future__ import annotations

import threading
from bisect import bisect_left
from dataclasses import dataclass, field
from datetime import UTC, datetime

from dev_workspace_mcp.config import get_settings
from dev_workspace_mcp.models.services import GetLogsResponse, LogLine


@dataclass(slots=True)
class ServiceLogBuffer:
    lines: list[LogLine] = field(default_factory=list)
    total_bytes: int = 0
    next_line_number: int = 0
    open_line_numbers: dict[str, int] = field(default_factory=dict)


class ServiceLogStore:
    """Accumulates bounded in-memory log buffers per service."""

    def __init__(self, *, max_bytes: int | None = None) -> None:
        self._lines: dict[str, ServiceLogBuffer] = {}
        self._lock = threading.Lock()
        self._max_bytes = get_settings().max_log_bytes if max_bytes is None else max_bytes

    def append(self, key: str, stream: str, text: str) -> None:
        """Append one or more complete log lines for a service."""

        if not text:
            return
        with self._lock:
            bucket = self._lines.setdefault(key, ServiceLogBuffer())
            for raw_line in text.splitlines() or [text]:
                message = _truncate_text(raw_line, max_bytes=self._max_bytes)
                self._append_line(bucket, stream, message)

    def set_open_fragment(self, key: str, stream: str, text: str) -> None:
        """Expose the current partial line while it is still being streamed."""

        if not text:
            return
        with self._lock:
            bucket = self._lines.setdefault(key, ServiceLogBuffer())
            message = _truncate_text(text, max_bytes=self._max_bytes)
            if bucket.open_line_numbers.get(stream) is None:
                line = self._append_line(bucket, stream, message)
                bucket.open_line_numbers[stream] = line.line_number
                return
            self._update_line(bucket, bucket.open_line_numbers[stream], stream, message)

    def close_open_fragment(self, key: str, stream: str, text: str) -> None:
        """Finalize the currently open partial line with its latest full text."""

        if not text:
            self.clear_open_fragment(key, stream)
            return
        with self._lock:
            bucket = self._lines.setdefault(key, ServiceLogBuffer())
            message = _truncate_text(text, max_bytes=self._max_bytes)
            if bucket.open_line_numbers.get(stream) is None:
                self._append_line(bucket, stream, message)
                return
            self._update_line(bucket, bucket.open_line_numbers[stream], stream, message)
            bucket.open_line_numbers.pop(stream, None)

    def clear_open_fragment(self, key: str, stream: str) -> None:
        with self._lock:
            bucket = self._lines.get(key)
            if bucket is not None:
                bucket.open_line_numbers.pop(stream, None)

    def slice(self, key: str, *, offset: int = 0, limit: int = 200) -> GetLogsResponse:
        with self._lock:
            buffer = self._lines.get(key)
            lines = [] if buffer is None else buffer.lines
            start = 0
            if lines:
                line_numbers = [line.line_number or 0 for line in lines]
                start = bisect_left(line_numbers, offset)
            selected = lines[start : start + limit]
            next_offset = (
                selected[-1].line_number + 1
                if start + limit < len(lines) and selected
                else None
            )
            return GetLogsResponse(
                service_name=key.split(":", 1)[1] if ":" in key else key,
                lines=[line.model_copy(deep=True) for line in selected],
                next_offset=next_offset,
                truncated=next_offset is not None,
            )

    def _append_line(self, bucket: ServiceLogBuffer, stream: str, message: str) -> LogLine:
        line = LogLine(
            message=message,
            stream=stream,
            line_number=bucket.next_line_number,
            timestamp=datetime.now(UTC),
        )
        bucket.lines.append(line)
        bucket.next_line_number += 1
        bucket.total_bytes += _line_size_bytes(message)
        _trim_log_buffer(bucket, max_bytes=self._max_bytes)
        return line

    def _update_line(
        self,
        bucket: ServiceLogBuffer,
        line_number: int,
        stream: str,
        message: str,
    ) -> None:
        index = _find_line_index(bucket, line_number)
        if index is None:
            line = self._append_line(bucket, stream, message)
            bucket.open_line_numbers[stream] = line.line_number
            return

        current = bucket.lines[index]
        bucket.total_bytes -= _line_size_bytes(current.message)
        bucket.lines[index] = current.model_copy(
            update={
                "message": message,
                "stream": stream,
                "timestamp": datetime.now(UTC),
            },
            deep=True,
        )
        bucket.total_bytes += _line_size_bytes(message)
        _trim_log_buffer(bucket, max_bytes=self._max_bytes)



def _find_line_index(buffer: ServiceLogBuffer, line_number: int) -> int | None:
    for index, line in enumerate(buffer.lines):
        if line.line_number == line_number:
            return index
    return None



def _trim_log_buffer(buffer: ServiceLogBuffer, *, max_bytes: int | None) -> None:
    if max_bytes is None:
        return
    while buffer.lines and buffer.total_bytes > max_bytes:
        removed = buffer.lines.pop(0)
        buffer.total_bytes -= _line_size_bytes(removed.message)
        if buffer.open_line_numbers:
            buffer.open_line_numbers = {
                stream: line_number
                for stream, line_number in buffer.open_line_numbers.items()
                if line_number != removed.line_number
            }



def _truncate_text(text: str, *, max_bytes: int | None) -> str:
    if max_bytes is None:
        return text
    max_payload_bytes = max(max_bytes - 1, 0)
    encoded = text.encode("utf-8")
    if len(encoded) <= max_payload_bytes:
        return text
    return encoded[:max_payload_bytes].decode("utf-8", errors="ignore")



def _line_size_bytes(text: str) -> int:
    return len(text.encode("utf-8")) + 1


__all__ = ["ServiceLogStore"]
