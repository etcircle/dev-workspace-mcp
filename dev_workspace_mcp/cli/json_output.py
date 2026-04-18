from __future__ import annotations

import json
import sys
from typing import Any, TextIO


def render_json(payload: Any, *, pretty: bool = False) -> str:
    if pretty:
        return json.dumps(payload, indent=2, sort_keys=True) + "\n"
    return json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n"


def write_json(
    payload: Any,
    *,
    stream: TextIO | None = None,
    pretty: bool = False,
) -> None:
    target = stream or sys.stdout
    target.write(render_json(payload, pretty=pretty))


__all__ = ["render_json", "write_json"]
