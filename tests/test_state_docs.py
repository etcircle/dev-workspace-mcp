from __future__ import annotations

from dev_workspace_mcp.config import Settings
from dev_workspace_mcp.mcp_server.tool_registry import build_tool_registry
from dev_workspace_mcp.projects.registry import ProjectRegistry


def test_read_write_and_patch_state_doc_tools(workspace_root, make_manifest_project) -> None:
    make_manifest_project()
    registry = ProjectRegistry(Settings(workspace_roots=[str(workspace_root)]))
    registry.refresh()
    tools = build_tool_registry(registry)

    write_result = tools.run(
        "write_state_doc",
        project_id="manifest-id",
        kind="memory",
        raw_markdown="# Current Truth\nAlpha\n",
    )
    assert write_result["ok"] is True
    assert write_result["data"]["document"]["path"] == ".devworkspace/memory.md"
    assert write_result["data"]["document"]["char_count"] > 0

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



def test_state_doc_limit_is_enforced(workspace_root, make_manifest_project) -> None:
    make_manifest_project()
    registry = ProjectRegistry(Settings(workspace_roots=[str(workspace_root)]))
    registry.refresh()
    tools = build_tool_registry(registry)

    result = tools.run(
        "write_state_doc",
        project_id="manifest-id",
        kind="memory",
        raw_markdown="x" * 4_001,
    )

    assert result["ok"] is False
    assert result["error"]["code"] == "STATE_DOC_LIMIT_EXCEEDED"
