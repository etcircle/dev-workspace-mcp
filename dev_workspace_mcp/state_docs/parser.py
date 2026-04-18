from __future__ import annotations

from collections import OrderedDict


def parse_state_document(text: str) -> dict[str, str]:
    """Split a markdown document into simple top-level heading sections."""

    sections: OrderedDict[str, list[str]] = OrderedDict()
    current_heading: str | None = None
    body: list[str] = []

    for line in text.splitlines():
        if line.startswith("# "):
            current_heading = line[2:].strip()
            sections.setdefault(current_heading, [])
            continue
        if current_heading is None:
            body.append(line)
            continue
        sections.setdefault(current_heading, []).append(line)

    parsed = OrderedDict()
    if body:
        parsed["body"] = "\n".join(body).strip()
    for heading, lines in sections.items():
        parsed[heading] = "\n".join(lines).strip()
    return dict(parsed)



def patch_state_document(
    text: str,
    section_updates: dict[str, str],
    *,
    create_missing_sections: bool = True,
) -> str:
    """Replace or append top-level heading sections in a markdown document."""

    parsed = parse_state_document(text)
    body = parsed.pop("body", "")

    ordered_sections: OrderedDict[str, str] = OrderedDict(parsed)
    for heading, content in section_updates.items():
        if heading in ordered_sections or create_missing_sections:
            ordered_sections[heading] = content.strip()

    parts: list[str] = []
    if body:
        parts.append(body.strip())
    for heading, content in ordered_sections.items():
        section = f"# {heading}".rstrip()
        if content:
            section = f"{section}\n{content.strip()}"
        parts.append(section)

    rendered = "\n\n".join(part for part in parts if part).strip()
    return f"{rendered}\n" if rendered else ""


__all__ = ["parse_state_document", "patch_state_document"]
