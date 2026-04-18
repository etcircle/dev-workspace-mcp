from __future__ import annotations

from dev_workspace_mcp.config import Settings
from dev_workspace_mcp.mcp_server.tool_registry import build_tool_registry
from dev_workspace_mcp.projects.registry import ProjectRegistry


def test_write_read_list_patch_move_and_delete_file_tools(
    workspace_root,
    make_manifest_project,
) -> None:
    make_manifest_project()
    registry = ProjectRegistry(Settings(workspace_roots=[str(workspace_root)]))
    registry.refresh()
    tools = build_tool_registry(registry)

    write_result = tools.run(
        "write_file",
        project_id="manifest-id",
        path="src/app.py",
        content="line1\nline2\n",
    )
    assert write_result["ok"] is True
    assert write_result["data"]["path"] == "src/app.py"
    assert write_result["data"]["bytes_written"] > 0

    read_result = tools.run(
        "read_file",
        project_id="manifest-id",
        path="src/app.py",
        offset=1,
        limit=1,
    )
    assert read_result["ok"] is True
    assert read_result["data"]["content"] == "line1"
    assert read_result["data"]["summary"]["line_count"] == 2

    list_result = tools.run("list_dir", project_id="manifest-id", path="src")
    assert list_result["ok"] is True
    assert list_result["data"]["path"] == "src"
    assert [entry["name"] for entry in list_result["data"]["entries"]] == ["app.py"]

    patch_result = tools.run(
        "apply_patch",
        project_id="manifest-id",
        patch=(
            "--- a/src/app.py\n"
            "+++ b/src/app.py\n"
            "@@ -1,2 +1,2 @@\n"
            "-line1\n"
            "+line1 changed\n"
            " line2\n"
        ),
    )
    assert patch_result["ok"] is True
    assert patch_result["data"]["changed_paths"] == ["src/app.py"]

    patched_read = tools.run("read_file", project_id="manifest-id", path="src/app.py")
    assert patched_read["ok"] is True
    assert patched_read["data"]["content"] == "line1 changed\nline2\n"

    move_result = tools.run(
        "move_path",
        project_id="manifest-id",
        source_path="src/app.py",
        destination_path="src/renamed.py",
    )
    assert move_result["ok"] is True
    assert move_result["data"]["path"] == "src/renamed.py"
    assert move_result["data"]["changed"] is True

    moved_read = tools.run("read_file", project_id="manifest-id", path="src/renamed.py")
    assert moved_read["ok"] is True
    assert moved_read["data"]["content"] == "line1 changed\nline2\n"

    delete_result = tools.run(
        "delete_path",
        project_id="manifest-id",
        path="src/renamed.py",
    )
    assert delete_result["ok"] is True
    assert delete_result["data"]["path"] == "src/renamed.py"
    assert delete_result["data"]["changed"] is True

    missing_read = tools.run("read_file", project_id="manifest-id", path="src/renamed.py")
    assert missing_read["ok"] is False
    assert missing_read["error"]["code"] == "PATH_NOT_FOUND"



def test_file_tools_reject_path_traversal(workspace_root, make_manifest_project) -> None:
    make_manifest_project()
    registry = ProjectRegistry(Settings(workspace_roots=[str(workspace_root)]))
    registry.refresh()
    tools = build_tool_registry(registry)

    result = tools.run(
        "read_file",
        project_id="manifest-id",
        path="../outside.txt",
    )

    assert result["ok"] is False
    assert result["error"]["code"] == "INVALID_PATH"
