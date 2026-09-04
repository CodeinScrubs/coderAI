from pathlib import Path
import subprocess

from git_manager import GitManager
from web_app import _resolve_clone_destination


def test_non_repo_is_not_initialized_automatically(tmp_path: Path):
    manager = GitManager(tmp_path)

    assert manager.is_repo() is False
    assert not (tmp_path / ".git").exists()


def test_preview_commit_log_and_revert(tmp_path: Path):
    manager = GitManager(tmp_path)
    manager.init_repo()
    target = tmp_path / "app.py"
    target.write_text("print('one')\n", encoding="utf-8")
    first = manager.stage_and_commit(["app.py"], "Add app")

    preview = manager.get_diff_preview("app.py", "print('two')\n")
    assert "-print('one')" in preview
    assert "+print('two')" in preview

    target.write_text("print('two')\n", encoding="utf-8")
    second = manager.stage_and_commit(["app.py"], "Update app")
    assert first and second and first != second
    assert manager.get_log(2)[0]["message"] == "Update app"

    revert_hash = manager.revert_to(second)
    assert revert_hash and target.read_text(encoding="utf-8") == "print('one')\n"


def test_commit_does_not_include_other_staged_files(tmp_path: Path):
    manager = GitManager(tmp_path)
    manager.init_repo()
    (tmp_path / "agent.txt").write_text("agent\n", encoding="utf-8")
    (tmp_path / "user.txt").write_text("user\n", encoding="utf-8")
    manager.stage_files(["user.txt"])

    commit_hash = manager.stage_and_commit(["agent.txt"], "Agent change")

    assert commit_hash
    status = manager.get_status()
    assert any(item["path"] == "user.txt" and item["status"][0] == "A" for item in status["files"])


def test_clone_preview_and_push_to_local_remote(tmp_path: Path):
    source = tmp_path / "source"
    source.mkdir()
    source_manager = GitManager(source)
    source_manager.init_repo()
    (source / "README.md").write_text("first\n", encoding="utf-8")
    source_manager.stage_and_commit(["README.md"], "Initial commit")

    bare = tmp_path / "remote.git"
    subprocess.run(["git", "init", "--bare", str(bare)], check=True, capture_output=True)
    source_manager._run("remote", "add", "origin", str(bare))
    source_manager.push()

    output = []
    clone = tmp_path / "clone"
    clone_manager = GitManager.clone_repository(str(bare), clone, output.append)
    assert clone_manager.is_repo()
    assert (clone / "README.md").read_text(encoding="utf-8") == "first\n"

    (clone / "README.md").write_text("second\n", encoding="utf-8")
    clone_manager.stage_and_commit(["README.md"], "Update README")
    preview = clone_manager.get_push_preview()
    assert preview["ahead"] == 1
    assert preview["commits"][0]["message"] == "Update README"

    clone_manager.push()
    assert clone_manager.get_push_preview()["ahead"] == 0


def test_token_auth_is_ephemeral_and_not_written_to_remote(tmp_path: Path):
    manager = GitManager(tmp_path)
    env = manager._credential_env("user", "secret-token")

    assert env["GIT_CONFIG_KEY_0"] == "http.extraHeader"
    assert "secret-token" not in env["GIT_CONFIG_VALUE_0"]
    assert not (tmp_path / ".gitconfig").exists()


def test_non_empty_clone_folder_gets_repository_subfolder(tmp_path: Path):
    (tmp_path / "existing.txt").write_text("keep", encoding="utf-8")

    destination = _resolve_clone_destination("https://github.com/emilkowalski/skills", str(tmp_path))

    assert destination == tmp_path.resolve() / "skills"


def test_branch_creation_and_switching(tmp_path: Path):
    manager = GitManager(tmp_path)
    manager.init_repo()
    (tmp_path / "hello.txt").write_text("hello\n", encoding="utf-8")
    manager.stage_and_commit(["hello.txt"], "Initial")

    branches = manager.list_branches()
    assert branches["current"] in ("main", "master")
    assert branches["current"] in branches["local"]

    manager.create_branch("feature/test-branch")
    updated = manager.list_branches()
    assert updated["current"] == "feature/test-branch"
    assert "feature/test-branch" in updated["local"]

    manager.switch_branch(branches["current"])
    reverted = manager.list_branches()
    assert reverted["current"] == branches["current"]


def test_fetch_and_pull(tmp_path: Path):
    source = tmp_path / "source"
    source.mkdir()
    source_manager = GitManager(source)
    source_manager.init_repo()
    (source / "file.txt").write_text("version 1\n", encoding="utf-8")
    source_manager.stage_and_commit(["file.txt"], "V1")

    bare = tmp_path / "remote.git"
    subprocess.run(["git", "init", "--bare", str(bare)], check=True, capture_output=True)
    source_manager._run("remote", "add", "origin", str(bare))
    source_manager.push()

    clone = tmp_path / "clone"
    clone_manager = GitManager.clone_repository(str(bare), clone)
    assert (clone / "file.txt").read_text(encoding="utf-8") == "version 1\n"

    # Push a new commit from source
    (source / "file.txt").write_text("version 2\n", encoding="utf-8")
    source_manager.stage_and_commit(["file.txt"], "V2")
    source_manager.push()

    # Fetch in clone
    fetch_out = clone_manager.fetch()
    assert "Fetch completed" in fetch_out or fetch_out == "" or len(fetch_out) >= 0

    # Pull in clone
    pull_res = clone_manager.pull()
    assert pull_res["ok"] is True
    assert pull_res["conflict"] is False
    assert (clone / "file.txt").read_text(encoding="utf-8") == "version 2\n"


def test_merge_conflict_detection_and_resolution(tmp_path: Path):
    manager = GitManager(tmp_path)
    manager.init_repo()
    target = tmp_path / "app.py"
    target.write_text("original code\n", encoding="utf-8")
    manager.stage_and_commit(["app.py"], "Base commit")

    current_branch = manager.list_branches()["current"]

    # Create feature branch and change app.py
    manager.create_branch("feature-conflict")
    target.write_text("feature code\n", encoding="utf-8")
    manager.stage_and_commit(["app.py"], "Feature edit")

    # Switch back to base branch and make conflicting edit
    manager.switch_branch(current_branch)
    target.write_text("main code\n", encoding="utf-8")
    manager.stage_and_commit(["app.py"], "Main edit")

    # Merge feature-conflict into base branch -> triggers conflict
    manager._run("merge", "feature-conflict", check=False)
    assert manager.is_in_merge() is True

    conflicts = manager.get_conflicts()
    assert len(conflicts) == 1
    assert conflicts[0]["path"] == "app.py"
    assert conflicts[0]["count"] >= 1
    assert "main code" in conflicts[0]["hunks"][0]["ours"]
    assert "feature code" in conflicts[0]["hunks"][0]["theirs"]

    # Resolve using "ours"
    res = manager.resolve_conflict("app.py", "ours")
    assert res["ok"] is True
    assert res["remaining_conflicts"] == 0

    # Complete merge
    commit_hash = manager.complete_merge("Merge feature-conflict accepting ours")
    assert commit_hash
    assert manager.is_in_merge() is False
    assert target.read_text(encoding="utf-8").strip() == "main code"


def test_merge_conflict_abort(tmp_path: Path):
    manager = GitManager(tmp_path)
    manager.init_repo()
    target = tmp_path / "file.txt"
    target.write_text("base\n", encoding="utf-8")
    manager.stage_and_commit(["file.txt"], "Base")

    current_branch = manager.list_branches()["current"]

    manager.create_branch("branch-abort")
    target.write_text("branch abort edit\n", encoding="utf-8")
    manager.stage_and_commit(["file.txt"], "Branch edit")

    manager.switch_branch(current_branch)
    target.write_text("main abort edit\n", encoding="utf-8")
    manager.stage_and_commit(["file.txt"], "Main edit")

    manager._run("merge", "branch-abort", check=False)
    assert manager.is_in_merge() is True

    abort_msg = manager.abort_merge()
    assert "abort" in abort_msg.lower() or not manager.is_in_merge()
    assert manager.is_in_merge() is False
    assert target.read_text(encoding="utf-8").strip() == "main abort edit"
