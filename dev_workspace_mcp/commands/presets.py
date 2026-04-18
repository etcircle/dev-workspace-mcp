from __future__ import annotations

from collections.abc import Mapping, Sequence


class CommandPresetRegistry:
    """Stores named command presets for later resolution."""

    def __init__(self, presets: Mapping[str, Sequence[str]] | None = None) -> None:
        self._presets = {name: list(argv) for name, argv in (presets or {}).items()}

    def get_argv(self, preset_name: str) -> list[str]:
        """Return a copy of a preset command argv list."""

        return list(self._presets.get(preset_name, []))

    def has_preset(self, preset_name: str) -> bool:
        """Return whether the preset is currently defined."""

        return preset_name in self._presets

    def list_presets(self) -> list[str]:
        return sorted(self._presets)


__all__ = ["CommandPresetRegistry"]
