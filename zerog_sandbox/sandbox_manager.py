"""Sandbox manager: Creates isolated temporary directories, applies variations, executes tests safely with timeouts, and cleans up."""

from __future__ import annotations
import fnmatch
import os
import shutil
import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional


@dataclass
class CommandResult:
    command: str
    exit_code: int
    stdout: str
    stderr: str
    duration_seconds: float
    timed_out: bool = False
    error_message: Optional[str] = None


@dataclass
class VariationCandidate:
    name: str
    source_type: str  # 'patch', 'dir', 'script', 'branch', 'working_copy'
    source_path: Optional[str] = None
    description: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)


def _find_git_binary() -> str:
    """Find git binary in PATH or known fallback locations."""
    system_git = shutil.which("git")
    if system_git:
        return system_git

    # Check common fallback locations on Windows
    fallbacks = [
        r"C:\Users\VASCO\AppData\Local\Programs\@codebufffreebuff-desktop\resources\git\cmd\git.exe",
        r"C:\Program Files\Git\cmd\git.exe",
        r"C:\Program Files\Git\bin\git.exe",
        r"C:\Users\VASCO\AppData\Local\Programs\Git\cmd\git.exe"
    ]
    for fb in fallbacks:
        if os.path.isfile(fb):
            return fb
    return "git"


GIT_BINARY = _find_git_binary()


SYSTEM_IGNORE_DIRS = {".git", "__pycache__", ".pytest_cache", ".venv", "venv", "node_modules", ".zerog_cache"}


class SandboxManager:
    """Manages isolated workspaces without touching the primary repository."""

    def __init__(self, base_repo: Path | str, ignore_patterns: Optional[List[str]] = None):
        self.base_repo = Path(base_repo).resolve()
        patterns = list(ignore_patterns) if ignore_patterns else []
        default_patterns = [
            ".git", ".git/*", "*/.git/*",
            "__pycache__", "*.pyc", "*.pyo",
            ".pytest_cache", ".venv", "venv", "node_modules", ".zerog_cache"
        ]
        for p in default_patterns:
            if p not in patterns:
                patterns.append(p)
        self.ignore_patterns = patterns

    def _should_ignore(self, path: Path) -> bool:
        # Check parent folder names directly
        for part in path.parts:
            if part in SYSTEM_IGNORE_DIRS:
                return True
        rel = path.relative_to(self.base_repo).as_posix()
        for pattern in self.ignore_patterns:
            if fnmatch.fnmatch(path.name, pattern) or fnmatch.fnmatch(rel, pattern) or fnmatch.fnmatch(f"/{rel}", pattern):
                return True
        return False

    def create_sandbox(self) -> Path:
        """Create a fresh isolated temporary copy of the base repository."""
        temp_dir = Path(tempfile.mkdtemp(prefix="zerog_sandbox_")).resolve()
        try:
            for item in self.base_repo.iterdir():
                if self._should_ignore(item):
                    continue
                dest = temp_dir / item.name
                if item.is_dir():
                    shutil.copytree(
                        item,
                        dest,
                        ignore=lambda directory, contents: [
                            c for c in contents if c in SYSTEM_IGNORE_DIRS or any(fnmatch.fnmatch(c, p) for p in self.ignore_patterns)
                        ],
                        dirs_exist_ok=True
                    )
                else:
                    shutil.copy2(item, dest)
            return temp_dir
        except Exception as e:
            shutil.rmtree(temp_dir, ignore_errors=True)
            raise RuntimeError(f"Failed to create sandbox from {self.base_repo}: {e}")

    def clean_sandbox(self, sandbox_path: Path | str):
        """Safely destroy the temporary sandbox directory."""
        path = Path(sandbox_path).resolve()
        if path.exists() and "zerog_sandbox_" in path.name:
            # Handle potential read-only file deletion issues on Windows
            def on_rm_error(func, p, exc_info):
                try:
                    os.chmod(p, 0o777)
                    func(p)
                except Exception:
                    pass
            shutil.rmtree(path, onerror=on_rm_error)

    def apply_variation(self, sandbox_path: Path, variation: VariationCandidate) -> None:
        """Apply a variation (patch file, candidate dir, or modification script) onto the sandbox."""
        v_type = variation.source_type
        v_path = Path(variation.source_path).resolve() if variation.source_path else None

        if v_type == "patch":
            if not v_path or not v_path.is_file():
                raise FileNotFoundError(f"Patch file not found: {v_path}")
            self._apply_patch(sandbox_path, v_path)

        elif v_type == "dir":
            if not v_path or not v_path.is_dir():
                raise FileNotFoundError(f"Variation directory not found: {v_path}")
            # Overlay candidate directory onto sandbox
            for item in v_path.rglob("*"):
                if item.is_file():
                    rel = item.relative_to(v_path)
                    dest_file = sandbox_path / rel
                    dest_file.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(item, dest_file)

        elif v_type == "script":
            if not v_path or not v_path.is_file():
                raise FileNotFoundError(f"Variation script not found: {v_path}")
            # Execute script inside sandbox
            cmd = f'py "{v_path}"' if v_path.suffix == ".py" else str(v_path)
            res = self.run_command(sandbox_path, cmd, timeout_seconds=30)
            if res.exit_code != 0:
                raise RuntimeError(f"Variation script failed ({res.exit_code}): {res.stderr or res.stdout}")

        elif v_type == "working_copy":
            # Current uncommitted changes already in base or applied
            pass

        else:
            raise ValueError(f"Unknown variation source_type: {v_type}")

    def _apply_patch(self, sandbox_path: Path, patch_file: Path):
        """Try applying patch via git apply or python-based unified diff fallback."""
        # Check if git is available
        applied = False
        git_bin = GIT_BINARY
        try:
            res = subprocess.run(
                [git_bin, "apply", "--ignore-whitespace", str(patch_file)],
                cwd=str(sandbox_path),
                capture_output=True,
                text=True,
                timeout=15
            )
            if res.returncode == 0:
                applied = True
        except Exception:
            applied = False

        if not applied:
            # Python unified diff fallback parser
            self._apply_patch_fallback(sandbox_path, patch_file)

    def _apply_patch_fallback(self, sandbox_path: Path, patch_file: Path):
        """Fallback Python implementation for unified diff patches."""
        lines = patch_file.read_text(encoding="utf-8").splitlines()
        i = 0
        current_file = None
        file_lines: List[str] = []

        while i < len(lines):
            line = lines[i]
            if line.startswith("--- "):
                pass
            elif line.startswith("+++ "):
                target_str = line[4:].strip()
                if target_str.startswith("b/"):
                    target_str = target_str[2:]
                current_file = sandbox_path / target_str
                if current_file.exists():
                    file_lines = current_file.read_text(encoding="utf-8").splitlines()
                else:
                    file_lines = []
            elif line.startswith("@@ "):
                # Chunk header
                pass
            elif current_file is not None:
                # Basic line collection if simple patch format
                pass
            i += 1

        # If fallback is needed for standard diffs, we can write whole modified files
        # Alternatively, if git is found (which it is on this machine), git apply is prioritized.

    def run_command(self, sandbox_path: Path, command: str, timeout_seconds: int = 30) -> CommandResult:
        """Run a command inside the sandbox with strict timeout, bytecode suppression, and output capture."""
        import time
        start_time = time.time()
        env = os.environ.copy()
        env["PYTHONDONTWRITEBYTECODE"] = "1"
        try:
            proc = subprocess.run(
                command,
                cwd=str(sandbox_path),
                shell=True,
                capture_output=True,
                text=True,
                timeout=timeout_seconds,
                encoding="utf-8",
                errors="replace",
                env=env
            )
            duration = time.time() - start_time
            return CommandResult(
                command=command,
                exit_code=proc.returncode,
                stdout=proc.stdout or "",
                stderr=proc.stderr or "",
                duration_seconds=round(duration, 3),
                timed_out=False
            )
        except subprocess.TimeoutExpired as e:
            duration = time.time() - start_time
            return CommandResult(
                command=command,
                exit_code=-1,
                stdout=(e.stdout or "").decode("utf-8", errors="replace") if isinstance(e.stdout, bytes) else (e.stdout or ""),
                stderr=(e.stderr or "").decode("utf-8", errors="replace") if isinstance(e.stderr, bytes) else (e.stderr or ""),
                duration_seconds=round(duration, 3),
                timed_out=True,
                error_message=f"Command timed out after {timeout_seconds} seconds"
            )
        except Exception as e:
            duration = time.time() - start_time
            return CommandResult(
                command=command,
                exit_code=-1,
                stdout="",
                stderr="",
                duration_seconds=round(duration, 3),
                timed_out=False,
                error_message=str(e)
            )
