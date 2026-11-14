"""GitHub Exporter: Lands chosen variation, creates clean Git branch, commits, and opens/guides PR."""

from __future__ import annotations
import os
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from zerog_sandbox.sandbox_manager import GIT_BINARY, VariationCandidate, SandboxManager


@dataclass
class LandResult:
    success: bool
    branch_name: str
    commit_sha: Optional[str]
    pr_url: Optional[str]
    message: str
    gh_cli_available: bool
    manual_pr_commands: List[str]


class GitHubExporter:
    """Safely applies the winning variation to a git branch, commits, and handles PR creation."""

    def __init__(self, repo_dir: Path | str):
        self.repo_dir = Path(repo_dir).resolve()
        self.git_bin = GIT_BINARY

    def is_git_repo(self) -> bool:
        dot_git = self.repo_dir / ".git"
        return dot_git.is_dir() or dot_git.is_file()

    def run_git(self, args: List[str]) -> subprocess.CompletedProcess:
        env = os.environ.copy()
        env["PYTHONDONTWRITEBYTECODE"] = "1"
        return subprocess.run(
            [self.git_bin] + args,
            cwd=str(self.repo_dir),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            env=env
        )

    def clean_cache_files(self):
        """Remove transient Python byte-compiled artifacts from workspace before git operations."""
        for p in list(self.repo_dir.rglob("__pycache__")):
            if p.is_dir():
                shutil.rmtree(p, ignore_errors=True)
        for ext in ("*.pyc", "*.pyo"):
            for f in list(self.repo_dir.rglob(ext)):
                try:
                    f.unlink()
                except Exception:
                    pass

    def check_uncommitted_changes(self) -> Tuple[bool, str]:
        """Check if base repository has uncommitted tracked or untracked changes."""
        self.clean_cache_files()
        res = self.run_git(["status", "--porcelain"])
        if res.returncode == 0:
            lines = [
                line for line in res.stdout.splitlines()
                if not any(token in line for token in ("__pycache__", ".pyc", ".pyo"))
            ]
            clean_out = "\n".join(lines).strip()
            return (len(clean_out) > 0, clean_out)
        return (False, "")

    def is_gh_cli_available(self) -> bool:
        gh_bin = shutil.which("gh")
        if not gh_bin:
            return False
        try:
            res = subprocess.run([gh_bin, "auth", "status"], capture_output=True, text=True, timeout=5)
            return res.returncode == 0
        except Exception:
            return False

    def ensure_git_baseline(self):
        """Ensure the target repository is initialized with an initial commit."""
        self.clean_cache_files()
        if not self.is_git_repo():
            self.run_git(["init"])
            self.run_git(["config", "user.name", "VASCO (ZeroG Bot)"])
            self.run_git(["config", "user.email", "vasco@local.sandbox"])
            self.run_git(["add", "."])
            self.run_git(["commit", "-m", "chore: initial baseline commit before ZeroG"])
        else:
            # Check if repo has at least one commit
            head_check = self.run_git(["rev-parse", "--verify", "HEAD"])
            if head_check.returncode != 0:
                self.run_git(["config", "user.name", "VASCO (ZeroG Bot)"])
                self.run_git(["config", "user.email", "vasco@local.sandbox"])
                self.run_git(["add", "."])
                self.run_git(["commit", "-m", "chore: initial baseline commit before ZeroG"])

    def get_current_branch(self) -> str:
        """Get the current active git branch name."""
        res = self.run_git(["rev-parse", "--abbrev-ref", "HEAD"])
        if res.returncode == 0:
            return res.stdout.strip()
        return "main"

    def land_variation(
        self,
        variation: VariationCandidate,
        branch_name: str,
        commit_message: str,
        create_pr: bool = False,
        pr_title: Optional[str] = None,
        pr_body: Optional[str] = None,
        return_to_original_branch: bool = True
    ) -> LandResult:
        """Applies variation directly onto base repo in a clean branch, commits, and returns to original branch."""
        self.clean_cache_files()
        self.ensure_git_baseline()

        original_branch = self.get_current_branch()
        if original_branch == branch_name:
            original_branch = "master" if self.run_git(["rev-parse", "--verify", "master"]).returncode == 0 else "main"

        # Check for uncommitted changes
        has_uncommitted, status_out = self.check_uncommitted_changes()
        stashed = False
        if has_uncommitted:
            stash_res = self.run_git(["stash", "push", "-u", "-m", "ZeroG auto-stash before landing variation"])
            if stash_res.returncode == 0:
                stashed = True
            else:
                has_still, still_out = self.check_uncommitted_changes()
                if has_still:
                    return LandResult(
                        success=False,
                        branch_name=branch_name,
                        commit_sha=None,
                        pr_url=None,
                        message=f"Aborted: Uncommitted changes present and git stash failed:\n{still_out}",
                        gh_cli_available=False,
                        manual_pr_commands=[]
                    )

        # Make sure we branch from the clean baseline original branch (e.g., master/main)
        self.run_git(["checkout", original_branch])

        # Check out or create branch
        branch_res = self.run_git(["checkout", "-B", branch_name])
        if branch_res.returncode != 0:
            return LandResult(
                success=False,
                branch_name=branch_name,
                commit_sha=None,
                pr_url=None,
                message=f"Failed to create/checkout branch {branch_name}: {branch_res.stderr or branch_res.stdout}",
                gh_cli_available=False,
                manual_pr_commands=[]
            )

        v_type = variation.source_type
        v_path = Path(variation.source_path).resolve() if variation.source_path else None

        try:
            if v_type == "dir" and v_path and v_path.is_dir():
                for item in v_path.rglob("*"):
                    if item.is_file():
                        rel = item.relative_to(v_path)
                        dest = self.repo_dir / rel
                        dest.parent.mkdir(parents=True, exist_ok=True)
                        shutil.copy2(item, dest)
            elif v_type == "patch" and v_path and v_path.is_file():
                res = self.run_git(["apply", "--ignore-whitespace", str(v_path)])
                if res.returncode != 0:
                    raise RuntimeError(f"git apply failed: {res.stderr}")
            elif v_type == "script" and v_path and v_path.is_file():
                cmd = f'py "{v_path}"' if v_path.suffix == ".py" else str(v_path)
                env = os.environ.copy()
                env["PYTHONDONTWRITEBYTECODE"] = "1"
                subprocess.run(cmd, cwd=str(self.repo_dir), shell=True, check=True, env=env)
        except Exception as e:
            return LandResult(
                success=False,
                branch_name=branch_name,
                commit_sha=None,
                pr_url=None,
                message=f"Failed to apply variation files onto branch {branch_name}: {e}",
                gh_cli_available=False,
                manual_pr_commands=[]
            )

        self.clean_cache_files()
        self.run_git(["add", "."])
        commit_res = self.run_git(["commit", "-m", commit_message])
        sha_res = self.run_git(["rev-parse", "--short", "HEAD"])
        commit_sha = sha_res.stdout.strip() if sha_res.returncode == 0 else "HEAD"

        gh_available = self.is_gh_cli_available()
        pr_url = None
        manual_commands = [
            f"git push -u origin {branch_name}",
            f'gh pr create --title "{pr_title or commit_message}" --body "{pr_body or "Automated PR created by ZeroG-Sandbox."}"'
        ]

        if create_pr and gh_available:
            try:
                self.run_git(["push", "-u", "origin", branch_name])
                pr_cmd = [
                    shutil.which("gh") or "gh", "pr", "create",
                    "--title", pr_title or commit_message,
                    "--body", pr_body or f"PR landed by ZeroG-Sandbox from variation {variation.name}"
                ]
                pr_res = subprocess.run(pr_cmd, cwd=str(self.repo_dir), capture_output=True, text=True, timeout=15)
                if pr_res.returncode == 0:
                    pr_url = pr_res.stdout.strip()
            except Exception:
                pr_url = None

        msg = f"Successfully landed '{variation.name}' on branch '{branch_name}' (commit: {commit_sha})."
        if pr_url:
            msg += f"\nGitHub PR created: {pr_url}"
        elif create_pr:
            msg += f"\nGitHub PR could not be created automatically (gh CLI or remote not authenticated). Run commands manually:\n" + "\n".join(manual_commands)

        # Return to original baseline branch so working directory remains unpolluted
        if return_to_original_branch and original_branch:
            self.run_git(["checkout", original_branch])
            if stashed:
                self.run_git(["stash", "pop"])
            msg += f"\nActive workspace returned to '{original_branch}'. Branch '{branch_name}' is ready."

        return LandResult(
            success=True,
            branch_name=branch_name,
            commit_sha=commit_sha,
            pr_url=pr_url,
            message=msg,
            gh_cli_available=gh_available,
            manual_pr_commands=manual_commands
        )

    def generate_workflow_template(self, dest_path: Optional[Path] = None) -> Path:
        """Generates sample GitHub Actions workflow for automated ZeroG verification."""
        workflow_content = """name: ZeroG Blast-Radius Verification

on:
  pull_request:
    branches: [ main, master, develop ]

jobs:
  zerog-analysis:
    name: Blast-Radius & Impact Gate
    runs-on: ubuntu-latest

    steps:
      - name: Checkout Code
        uses: actions/checkout@v4
        with:
          fetch-depth: 0

      - name: Setup Python
        uses: actions/setup-python@v5
        with:
          python-version: '3.11'

      - name: Run ZeroG Simulator Check
        run: |
          py -m zerog_sandbox.cli simulate --repo . --threshold 50
"""
        target = dest_path or (self.repo_dir / ".github" / "workflows" / "zerog-check.yml")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(workflow_content.strip(), encoding="utf-8")
        return target
