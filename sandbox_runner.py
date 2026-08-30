"""
sandbox_runner.py - Secure code execution runner with Docker container isolation and local process sandboxing.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import uuid
from pathlib import Path
from typing import NamedTuple


class ExecutionResult(NamedTuple):
    stdout: str
    stderr: str
    exit_code: int
    timed_out: bool
    used_sandbox: str  # "docker" or "local"


class SandboxRunner:
    """Executes code or shell commands either inside an isolated Docker container

    or via a local sandboxed subprocess with guardrails.
    """

    def __init__(
        self,
        workspace_path: str | Path,
        mode: str = "auto",  # "auto", "docker", "local"
        docker_image: str = "python:3.11-slim",
        memory_limit: str = "512m",
        cpu_limit: str = "1.0",
        pids_limit: int = 64,
        allow_network: bool = False,
        timeout_seconds: int = 20,
    ):
        self.workspace_path = Path(workspace_path).resolve()
        self.mode = mode.lower()
        self.docker_image = docker_image
        self.memory_limit = memory_limit
        self.cpu_limit = cpu_limit
        self.pids_limit = pids_limit
        self.allow_network = allow_network
        self.timeout_seconds = timeout_seconds

    @staticmethod
    def is_docker_available() -> bool:
        """Check if Docker CLI is installed and the Docker daemon is responsive."""
        if not shutil.which("docker"):
            return False
        try:
            res = subprocess.run(
                ["docker", "info"],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=3,
                text=True,
            )
            return res.returncode == 0
        except Exception:
            return False

    def get_effective_mode(self) -> str:
        """Determine whether to use docker or local execution based on configuration and system state."""
        if self.mode == "docker":
            return "docker"
        if self.mode == "local":
            return "local"
        # mode == "auto"
        return "docker" if self.is_docker_available() else "local"

    def run_python_code(
        self,
        code: str,
        env: dict[str, str] | None = None,
        process_register_cb=None,
    ) -> ExecutionResult:
        """Run a Python script inside sandbox or locally."""
        script_name = f"__tmp_agent_{uuid.uuid4().hex[:8]}__.py"
        script_path = self.workspace_path / script_name
        try:
            script_path.write_text(code, encoding="utf-8")
            effective = self.get_effective_mode()
            if effective == "docker":
                return self._run_docker(["python", f"/workspace/{script_name}"], process_register_cb)
            return self._run_local([sys.executable or "python", str(script_path)], env, process_register_cb)
        finally:
            script_path.unlink(missing_ok=True)

    def run_bash_command(
        self,
        command: str,
        env: dict[str, str] | None = None,
        process_register_cb=None,
    ) -> ExecutionResult:
        """Run a shell command inside sandbox or locally."""
        effective = self.get_effective_mode()
        if effective == "docker":
            return self._run_docker(["sh", "-c", command], process_register_cb)
        return self._run_local_shell(command, env, process_register_cb)

    def _run_docker(self, container_cmd: list[str], process_register_cb=None) -> ExecutionResult:
        """Execute command inside Docker container with restricted capabilities and mounted workspace."""
        abs_ws = str(self.workspace_path)
        docker_cmd = [
            "docker", "run", "--rm",
            "-v", f"{abs_ws}:/workspace:rw",
            "-w", "/workspace",
            f"--memory={self.memory_limit}",
            f"--cpus={self.cpu_limit}",
            f"--pids-limit={self.pids_limit}",
        ]
        if not self.allow_network:
            docker_cmd.extend(["--network", "none"])

        docker_cmd.append(self.docker_image)
        docker_cmd.extend(container_cmd)

        proc = None
        try:
            proc = subprocess.Popen(
                docker_cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            if process_register_cb:
                process_register_cb(proc)
            stdout, stderr = proc.communicate(timeout=self.timeout_seconds)
            return ExecutionResult(
                stdout=stdout or "",
                stderr=stderr or "",
                exit_code=proc.returncode,
                timed_out=False,
                used_sandbox="docker",
            )
        except subprocess.TimeoutExpired:
            if proc:
                try:
                    proc.kill()
                except Exception:
                    pass
            return ExecutionResult(
                stdout="",
                stderr=f"Execution timed out after {self.timeout_seconds}s in Docker sandbox",
                exit_code=-1,
                timed_out=True,
                used_sandbox="docker",
            )
        except Exception as exc:
            return ExecutionResult(
                stdout="",
                stderr=f"Docker sandbox execution error: {exc}",
                exit_code=-1,
                timed_out=False,
                used_sandbox="docker",
            )

    def _run_local(self, cmd: list[str], env: dict[str, str] | None, process_register_cb=None) -> ExecutionResult:
        """Execute command locally with subprocess tracking."""
        proc = None
        try:
            proc = subprocess.Popen(
                cmd,
                cwd=str(self.workspace_path),
                env=env,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            if process_register_cb:
                process_register_cb(proc)
            stdout, stderr = proc.communicate(timeout=self.timeout_seconds)
            return ExecutionResult(
                stdout=stdout or "",
                stderr=stderr or "",
                exit_code=proc.returncode,
                timed_out=False,
                used_sandbox="local",
            )
        except subprocess.TimeoutExpired:
            if proc:
                try:
                    proc.kill()
                except Exception:
                    pass
            return ExecutionResult(
                stdout="",
                stderr=f"Execution timed out after {self.timeout_seconds}s",
                exit_code=-1,
                timed_out=True,
                used_sandbox="local",
            )
        except Exception as exc:
            return ExecutionResult(
                stdout="",
                stderr=f"Local execution error: {exc}",
                exit_code=-1,
                timed_out=False,
                used_sandbox="local",
            )

    def _run_local_shell(self, command: str, env: dict[str, str] | None, process_register_cb=None) -> ExecutionResult:
        """Execute shell command locally with subprocess tracking."""
        proc = None
        try:
            proc = subprocess.Popen(
                command,
                shell=True,
                cwd=str(self.workspace_path),
                env=env,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            if process_register_cb:
                process_register_cb(proc)
            stdout, stderr = proc.communicate(timeout=self.timeout_seconds)
            return ExecutionResult(
                stdout=stdout or "",
                stderr=stderr or "",
                exit_code=proc.returncode,
                timed_out=False,
                used_sandbox="local",
            )
        except subprocess.TimeoutExpired:
            if proc:
                try:
                    proc.kill()
                except Exception:
                    pass
            return ExecutionResult(
                stdout="",
                stderr=f"Execution timed out after {self.timeout_seconds}s",
                exit_code=-1,
                timed_out=True,
                used_sandbox="local",
            )
        except Exception as exc:
            return ExecutionResult(
                stdout="",
                stderr=f"Local execution error: {exc}",
                exit_code=-1,
                timed_out=False,
                used_sandbox="local",
            )
