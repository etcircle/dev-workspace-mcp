from __future__ import annotations

from pathlib import Path

from dev_workspace_mcp.config import Settings
from dev_workspace_mcp.mcp_server.tool_registry import build_tool_registry
from dev_workspace_mcp.projects.registry import ProjectRegistry


def _build_tools(workspace_root: Path):
    registry = ProjectRegistry(Settings(workspace_roots=[str(workspace_root)]))
    registry.refresh()
    return build_tool_registry(registry)


def _assert_path_denied(result: dict) -> None:
    assert result["ok"] is False
    assert result["error"]["code"] == "PATH_SYMLINK_DENIED"


def test_read_write_and_patch_state_doc_tools(workspace_root, make_manifest_project) -> None:
    project_root = make_manifest_project()
    tools = _build_tools(workspace_root)

    write_result = tools.run(
        "write_state_doc",
        project_id="manifest-id",
        kind="memory",
        raw_markdown="# Current Truth\nAlpha\n",
    )
    assert write_result["ok"] is True
    assert write_result["data"]["document"]["path"] == ".devworkspace/memory.md"
    assert write_result["data"]["document"]["char_count"] > 0
    assert (project_root / ".devworkspace" / "memory.md").read_text(
        encoding="utf-8"
    ) == "# Current Truth\nAlpha\n"

    read_result = tools.run("read_state_doc", project_id="manifest-id", kind="memory")
    assert read_result["ok"] is True
    assert read_result["data"]["document"]["raw_markdown"] == "# Current Truth\nAlpha\n"
    assert read_result["data"]["parsed_sections"] == {"Current Truth": "Alpha"}

    patch_result = tools.run(
        "patch_state_doc",
        project_id="manifest-id",
        kind="memory",
        section_updates={"Current Truth": "Beta", "Next Step": "Ship it"},
    )
    assert patch_result["ok"] is True
    assert patch_result["data"]["updated_headings"] == ["Current Truth", "Next Step"]

    reread = tools.run("read_state_doc", project_id="manifest-id", kind="memory")
    assert reread["data"]["parsed_sections"] == {
        "Current Truth": "Beta",
        "Next Step": "Ship it",
    }
    assert (project_root / ".devworkspace" / "memory.md").read_text(encoding="utf-8") == (
        "# Current Truth\nBeta\n\n# Next Step\nShip it\n"
    )

    patch_missing = tools.run(
        "patch_state_doc",
        project_id="manifest-id",
        kind="tasks",
        section_updates={"Now": "Do it"},
    )
    assert patch_missing["ok"] is True
    assert (project_root / ".devworkspace" / "tasks.md").read_text(
        encoding="utf-8"
    ) == "# Now\nDo it\n"



def test_state_doc_denies_symlinked_devworkspace_directory_on_read_write_and_patch(
    workspace_root,
    make_manifest_project,
) -> None:
    project_root = make_manifest_project()
    outside_dir = workspace_root / "outside-state-docs"
    outside_dir.mkdir()
    outside_memory = outside_dir / "memory.md"
    outside_memory.write_text("# Current Truth\nOutside\n", encoding="utf-8")
    (project_root / ".devworkspace").symlink_to(outside_dir, target_is_directory=True)

    tools = _build_tools(workspace_root)

    _assert_path_denied(tools.run("read_state_doc", project_id="manifest-id", kind="memory"))
    _assert_path_denied(
        tools.run(
            "write_state_doc",
            project_id="manifest-id",
            kind="memory",
            raw_markdown="# Current Truth\nInside\n",
        )
    )
    _assert_path_denied(
        tools.run(
            "patch_state_doc",
            project_id="manifest-id",
            kind="memory",
            section_updates={"Current Truth": "Patched"},
        )
    )
    assert outside_memory.read_text(encoding="utf-8") == "# Current Truth\nOutside\n"



def test_state_doc_denies_symlinked_state_doc_file_on_read_write_and_patch(
    workspace_root,
    make_manifest_project,
) -> None:
    project_root = make_manifest_project()
    outside_memory = workspace_root / "outside-memory.md"
    outside_memory.write_text("# Current Truth\nOutside\n", encoding="utf-8")
    state_docs_dir = project_root / ".devworkspace"
    state_docs_dir.mkdir()
    (state_docs_dir / "memory.md").symlink_to(outside_memory)

    tools = _build_tools(workspace_root)

    _assert_path_denied(tools.run("read_state_doc", project_id="manifest-id", kind="memory"))
    _assert_path_denied(
        tools.run(
            "write_state_doc",
            project_id="manifest-id",
            kind="memory",
            raw_markdown="# Current Truth\nInside\n",
        )
    )
    _assert_path_denied(
        tools.run(
            "patch_state_doc",
            project_id="manifest-id",
            kind="memory",
            section_updates={"Current Truth": "Patched"},
        )
    )
    assert outside_memory.read_text(encoding="utf-8") == "# Current Truth\nOutside\n"



def test_state_doc_limit_is_enforced(workspace_root, make_manifest_project) -> None:
    make_manifest_project()
    tools = _build_tools(workspace_root)

    result = tools.run(
        "write_state_doc",
        project_id="manifest-id",
        kind="memory",
        raw_markdown="x" * 4_001,
    )

    assert result["ok"] is False
    assert result["error"]["code"] == "STATE_DOC_LIMIT_EXCEEDED"
