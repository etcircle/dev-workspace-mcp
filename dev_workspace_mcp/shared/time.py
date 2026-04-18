from __future__ import annotations

from datetime import UTC, datetime


def utc_now() -> datetime:
    """Return the current timezone-aware UTC timestamp."""

    return datetime.now(UTC)


def format_timestamp(moment: datetime | None = None) -> str:
    """Format a timestamp in ISO 8601 form."""

    return (moment or utc_now()).isoformat()


__all__ = ["format_timestamp", "utc_now"]