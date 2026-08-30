import pytest
from pathlib import Path
from sandbox_runner import SandboxRunner, ExecutionResult


def test_sandbox_mode_resolution(tmp_path):
    runner_local = SandboxRunner(tmp_path, mode="local")
    assert runner_local.get_effective_mode() == "local"

    runner_docker = SandboxRunner(tmp_path, mode="docker")
    assert runner_docker.get_effective_mode() == "docker"

    runner_auto = SandboxRunner(tmp_path, mode="auto")
    effective = runner_auto.get_effective_mode()
    assert effective in ("docker", "local")


def test_sandbox_run_python_local(tmp_path):
    runner = SandboxRunner(tmp_path, mode="local", timeout_seconds=10)
    result = runner.run_python_code("print('Hello Sandbox')\n")
    assert result.exit_code == 0
    assert "Hello Sandbox" in result.stdout
    assert not result.timed_out
    assert result.used_sandbox == "local"

    # Verify temp file is cleaned up
    tmp_files = list(tmp_path.glob("__tmp_agent_*.py"))
    assert len(tmp_files) == 0


def test_sandbox_run_bash_local(tmp_path):
    runner = SandboxRunner(tmp_path, mode="local", timeout_seconds=10)
    result = runner.run_bash_command("echo Sandbox bash test")
    assert result.exit_code == 0
    assert "Sandbox bash test" in result.stdout
    assert result.used_sandbox == "local"


def test_sandbox_timeout_handling(tmp_path):
    runner = SandboxRunner(tmp_path, mode="local", timeout_seconds=1)
    result = runner.run_python_code("import time\ntime.sleep(5)\n")
    assert result.timed_out
    assert result.exit_code == -1
    assert "timed out" in result.stderr


def test_sandbox_docker_command_construction(tmp_path, monkeypatch):
    runner = SandboxRunner(
        tmp_path,
        mode="docker",
        docker_image="python:3.11-slim",
        memory_limit="256m",
        cpu_limit="0.5",
        allow_network=False,
    )
    # Mock subprocess.Popen inside _run_docker to inspect args
    called_args = []

    class DummyProc:
        returncode = 0
        def communicate(self, timeout=None):
            return "docker stdout", ""

    def mock_popen(args, **kwargs):
        called_args.append(args)
        return DummyProc()

    import subprocess
    monkeypatch.setattr(subprocess, "Popen", mock_popen)

    res = runner._run_docker(["python", "/workspace/test.py"])
    assert res.stdout == "docker stdout"
    assert len(called_args) == 1
    args = called_args[0]
    assert "docker" in args
    assert "run" in args
    assert "--memory=256m" in args
    assert "--cpus=0.5" in args
    assert "--network" in args
    assert "none" in args
    assert "python:3.11-slim" in args
