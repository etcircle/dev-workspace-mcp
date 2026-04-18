from __future__ import annotations


def normalize_newlines(text: str) -> str:
    """Normalize common newline variants to Unix style."""

    return text.replace("\r\n", "\n").replace("\r", "\n")


def truncate_text(text: str, max_chars: int, suffix: str = "...") -> str:
    """Trim text to a bounded character count."""

    if max_chars < 0:
        raise ValueError("max_chars must be non-negative")
    if len(text) <= max_chars:
        return text
    if max_chars <= len(suffix):
        return suffix[:max_chars]
    return text[: max_chars - len(suffix)] + suffix


__all__ = ["normalize_newlines", "truncate_text"]