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


def test_read_file_denies_symlink_to_file_outside_project(
    workspace_root,
    make_manifest_project,
) -> None:
    project_root = make_manifest_project()
    outside_file = workspace_root / "outside.txt"
    outside_file.write_text("secret\n", encoding="utf-8")
    (project_root / "escape.txt").symlink_to(outside_file)

    registry = ProjectRegistry(Settings(workspace_roots=[str(workspace_root)]))
    registry.refresh()
    tools = build_tool_registry(registry)

    result = tools.run("read_file", project_id="manifest-id", path="escape.txt")

    assert result["ok"] is False
    assert result["error"]["code"] == "PATH_OUTSIDE_PROJECT"


def test_list_dir_denies_symlink_to_directory_outside_project(
    workspace_root,
    make_manifest_project,
) -> None:
    project_root = make_manifest_project()
    outside_dir = workspace_root / "outside-dir"
    outside_dir.mkdir()
    (outside_dir / "secret.txt").write_text("secret\n", encoding="utf-8")
    (project_root / "linked").symlink_to(outside_dir, target_is_directory=True)

    registry = ProjectRegistry(Settings(workspace_roots=[str(workspace_root)]))
    registry.refresh()
    tools = build_tool_registry(registry)

    result = tools.run("list_dir", project_id="manifest-id", path="linked")

    assert result["ok"] is False
    assert result["error"]["code"] == "PATH_OUTSIDE_PROJECT"


def test_write_file_denies_symlink_traversal_by_default(
    workspace_root,
    make_manifest_project,
) -> None:
    project_root = make_manifest_project()
    outside_dir = workspace_root / "outside-write-dir"
    outside_dir.mkdir()
    (project_root / "linked").symlink_to(outside_dir, target_is_directory=True)

    registry = ProjectRegistry(Settings(workspace_roots=[str(workspace_root)]))
    registry.refresh()
    tools = build_tool_registry(registry)

    result = tools.run(
        "write_file",
        project_id="manifest-id",
        path="linked/new.txt",
        content="should not write\n",
    )

    assert result["ok"] is False
    assert result["error"]["code"] == "PATH_SYMLINK_DENIED"
    assert not (outside_dir / "new.txt").exists()


def test_write_file_allows_missing_leaf_under_in_project_parent(
    workspace_root,
    make_manifest_project,
) -> None:
    project_root = make_manifest_project()
    (project_root / "src").mkdir()

    registry = ProjectRegistry(Settings(workspace_roots=[str(workspace_root)]))
    registry.refresh()
    tools = build_tool_registry(registry)

    result = tools.run(
        "write_file",
        project_id="manifest-id",
        path="src/generated.py",
        content="print('ok')\n",
    )

    assert result["ok"] is True
    assert result["data"]["path"] == "src/generated.py"
    assert (project_root / "src" / "generated.py").read_text(encoding="utf-8") == "print('ok')\n"


def test_apply_patch_denies_symlink_source_escape(
    workspace_root,
    make_manifest_project,
) -> None:
    project_root = make_manifest_project()
    outside_file = workspace_root / "outside-patch.txt"
    outside_file.write_text("secret\n", encoding="utf-8")
    (project_root / "escape.txt").symlink_to(outside_file)

    registry = ProjectRegistry(Settings(workspace_roots=[str(workspace_root)]))
    registry.refresh()
    tools = build_tool_registry(registry)

    result = tools.run(
        "apply_patch",
        project_id="manifest-id",
        patch=(
            "--- a/escape.txt\n"
            "+++ b/escape.txt\n"
            "@@ -1 +1 @@\n"
            "-secret\n"
            "+mutated\n"
        ),
    )

    assert result["ok"] is False
    assert result["error"]["code"] == "PATH_SYMLINK_DENIED"
    assert outside_file.read_text(encoding="utf-8") == "secret\n"



def test_move_path_denies_symlink_source_escape(
    workspace_root,
    make_manifest_project,
) -> None:
    project_root = make_manifest_project()
    outside_file = workspace_root / "outside-move.txt"
    outside_file.write_text("secret\n", encoding="utf-8")
    (project_root / "escape.txt").symlink_to(outside_file)

    registry = ProjectRegistry(Settings(workspace_roots=[str(workspace_root)]))
    registry.refresh()
    tools = build_tool_registry(registry)

    result = tools.run(
        "move_path",
        project_id="manifest-id",
        source_path="escape.txt",
        destination_path="src/renamed.txt",
    )

    assert result["ok"] is False
    assert result["error"]["code"] == "PATH_SYMLINK_DENIED"
    assert outside_file.exists()
    assert (project_root / "escape.txt").is_symlink()



def test_delete_path_denies_symlink_source_escape(
    workspace_root,
    make_manifest_project,
) -> None:
    project_root = make_manifest_project()
    outside_file = workspace_root / "outside-delete.txt"
    outside_file.write_text("secret\n", encoding="utf-8")
    (project_root / "escape.txt").symlink_to(outside_file)

    registry = ProjectRegistry(Settings(workspace_roots=[str(workspace_root)]))
    registry.refresh()
    tools = build_tool_registry(registry)

    result = tools.run(
        "delete_path",
        project_id="manifest-id",
        path="escape.txt",
    )

    assert result["ok"] is False
    assert result["error"]["code"] == "PATH_SYMLINK_DENIED"
    assert outside_file.exists()
    assert (project_root / "escape.txt").is_symlink()
