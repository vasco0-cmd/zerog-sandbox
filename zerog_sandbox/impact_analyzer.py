"""Impact analyzer: Analyzes diffs, modified files, test outputs, imports, and critical module blast-radiuses."""

from __future__ import annotations
import ast
import difflib
import fnmatch
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Set, Tuple


@dataclass
class FileDiffMetric:
    path: str
    lines_added: int
    lines_deleted: int
    is_critical: bool
    is_new: bool
    is_deleted: bool


@dataclass
class TestMetrics:
    total_tests: int
    passed_tests: int
    failed_tests: int
    error_tests: int
    new_tests_added: int
    execution_time: float
    output_summary: str


@dataclass
class ImpactReport:
    variation_name: str
    files_changed_count: int
    total_lines_added: int
    total_lines_deleted: int
    critical_files_touched: List[str]
    file_metrics: List[FileDiffMetric]
    test_metrics: TestMetrics
    dependency_graph: Dict[str, List[str]]
    module_centrality: Dict[str, int]
    centrality_impact_score: float
    raw_diff: str
    compilation_ok: bool
    error: str = ""


EXCLUDE_SYSTEM_DIRS = {".git", "__pycache__", ".pytest_cache", ".venv", "venv", "node_modules", ".zerog_cache", "candidates", "variations", "patches"}


class ImpactAnalyzer:
    """Computes code diff metrics, module dependency graph centrality, and test outcomes."""

    def __init__(self, base_repo: Path, critical_files: List[str], ignore_patterns: List[str]):
        self.base_repo = Path(base_repo).resolve()
        self.critical_files = critical_files or []
        patterns = list(ignore_patterns) if ignore_patterns else []
        default_ignores = [
            ".git", ".git/*", "*/.git/*",
            "__pycache__", "*.pyc", "*.pyo",
            ".pytest_cache", ".venv", "venv", "node_modules", ".zerog_cache",
            "candidates", "candidates/*", "variations", "variations/*", "patches", "patches/*"
        ]
        for p in default_ignores:
            if p not in patterns:
                patterns.append(p)
        self.ignore_patterns = patterns

    def _should_ignore_file(self, rel_path: str, parts: Tuple[str, ...]) -> bool:
        if any(part in EXCLUDE_SYSTEM_DIRS for part in parts):
            return True
        for ign in self.ignore_patterns:
            if fnmatch.fnmatch(rel_path, ign) or fnmatch.fnmatch(os.path.basename(rel_path), ign) or fnmatch.fnmatch(f"/{rel_path}", ign):
                return True
        return False

    def _is_critical(self, file_rel_path: str) -> bool:
        normalized = file_rel_path.replace("\\", "/")
        filename = os.path.basename(normalized)
        for pattern in self.critical_files:
            pattern_norm = pattern.replace("\\", "/")
            if fnmatch.fnmatch(filename, pattern_norm) or fnmatch.fnmatch(normalized, pattern_norm):
                return True
        return False

    def build_import_graph(self, repo_path: Path) -> Tuple[Dict[str, List[str]], Dict[str, int]]:
        """Parses python AST imports across the repository and computes in-degree centrality."""
        graph: Dict[str, List[str]] = {}
        in_degree: Dict[str, int] = {}

        py_files = [
            f for f in repo_path.rglob("*.py")
            if not self._should_ignore_file(f.relative_to(repo_path).as_posix(), f.relative_to(repo_path).parts)
        ]
        module_names = {}
        for f in py_files:
            rel = f.relative_to(repo_path).as_posix()
            mod_name = rel.replace("/", ".").replace(".py", "")
            if mod_name.endswith(".__init__"):
                mod_name = mod_name[:-9]
            module_names[mod_name] = rel
            graph[rel] = []
            in_degree[rel] = 0

        for f in py_files:
            rel = f.relative_to(repo_path).as_posix()
            try:
                tree = ast.parse(f.read_text(encoding="utf-8", errors="ignore"))
                for node in ast.walk(tree):
                    if isinstance(node, ast.Import):
                        for alias in node.names:
                            target = alias.name
                            if target in module_names and module_names[target] != rel:
                                graph[rel].append(module_names[target])
                    elif isinstance(node, ast.ImportFrom):
                        target = node.module or ""
                        if target in module_names and module_names[target] != rel:
                            graph[rel].append(module_names[target])
            except Exception:
                pass

        # Calculate in-degree centrality (how many other modules depend on this one)
        for src, targets in graph.items():
            for t in targets:
                in_degree[t] = in_degree.get(t, 0) + 1

        return graph, in_degree

    def compare_directories(self, base_path: Path, sandbox_path: Path) -> Tuple[List[FileDiffMetric], str]:
        """Compares base repo and sandbox directory to extract diff metrics."""
        metrics: List[FileDiffMetric] = []
        full_diff_text: List[str] = []

        def get_files(d: Path) -> Set[str]:
            files = set()
            for p in d.rglob("*"):
                if p.is_file():
                    rel = p.relative_to(d).as_posix()
                    if self._should_ignore_file(rel, p.relative_to(d).parts):
                        continue
                    files.add(rel)
            return files

        base_files = get_files(base_path)
        sandbox_files = get_files(sandbox_path)
        all_files = sorted(base_files | sandbox_files)

        for rel in all_files:
            base_file = base_path / rel
            sandbox_file = sandbox_path / rel

            is_new = rel not in base_files
            is_deleted = rel not in sandbox_files
            is_crit = self._is_critical(rel)

            if is_new:
                content = sandbox_file.read_text(encoding="utf-8", errors="replace").splitlines(keepends=True)
                added = len(content)
                deleted = 0
                diff = difflib.unified_diff([], content, fromfile="/dev/null", tofile=f"b/{rel}")
                diff_str = "".join(diff)
                full_diff_text.append(diff_str)
                metrics.append(FileDiffMetric(
                    path=rel, lines_added=added, lines_deleted=deleted,
                    is_critical=is_crit, is_new=True, is_deleted=False
                ))
            elif is_deleted:
                content = base_file.read_text(encoding="utf-8", errors="replace").splitlines(keepends=True)
                added = 0
                deleted = len(content)
                diff = difflib.unified_diff(content, [], fromfile=f"a/{rel}", tofile="/dev/null")
                diff_str = "".join(diff)
                full_diff_text.append(diff_str)
                metrics.append(FileDiffMetric(
                    path=rel, lines_added=added, lines_deleted=deleted,
                    is_critical=is_crit, is_new=False, is_deleted=True
                ))
            else:
                base_content = base_file.read_text(encoding="utf-8", errors="replace").splitlines(keepends=True)
                sandbox_content = sandbox_file.read_text(encoding="utf-8", errors="replace").splitlines(keepends=True)

                if base_content != sandbox_content:
                    diff = list(difflib.unified_diff(
                        base_content, sandbox_content,
                        fromfile=f"a/{rel}", tofile=f"b/{rel}"
                    ))
                    diff_str = "".join(diff)
                    full_diff_text.append(diff_str)

                    added = sum(1 for line in diff if line.startswith("+") and not line.startswith("+++"))
                    deleted = sum(1 for line in diff if line.startswith("-") and not line.startswith("---"))
                    metrics.append(FileDiffMetric(
                        path=rel, lines_added=added, lines_deleted=deleted,
                        is_critical=is_crit, is_new=False, is_deleted=False
                    ))

        return metrics, "".join(full_diff_text)

    def parse_test_output(self, stdout: str, stderr: str, duration: float) -> TestMetrics:
        """Parses unittest or pytest test outputs to count total, passed, failed, and errors."""
        combined = (stdout + "\n" + stderr).strip()

        # Check standard python unittest output (Ran X tests in Ys ... OK or FAILED (failures=A, errors=B))
        ran_match = re.search(r"Ran (\d+) tests? in", combined)
        total = int(ran_match.group(1)) if ran_match else 0

        failed = 0
        errors = 0

        fail_match = re.search(r"failures=(\d+)", combined)
        if fail_match:
            failed = int(fail_match.group(1))

        err_match = re.search(r"errors=(\d+)", combined)
        if err_match:
            errors = int(err_match.group(1))

        # Check pytest format (e.g., 5 passed, 2 failed in 0.23s)
        pytest_passed = re.search(r"(\d+)\s+passed", combined)
        pytest_failed = re.search(r"(\d+)\s+failed", combined)
        pytest_errors = re.search(r"(\d+)\s+errors?", combined)

        if pytest_passed or pytest_failed or pytest_errors:
            passed_count = int(pytest_passed.group(1)) if pytest_passed else 0
            failed_count = int(pytest_failed.group(1)) if pytest_failed else 0
            error_count = int(pytest_errors.group(1)) if pytest_errors else 0
            total = passed_count + failed_count + error_count
            failed = failed_count
            errors = error_count
            passed = passed_count
        else:
            if "FAILED" in combined and (failed == 0 and errors == 0):
                failed = 1
            passed = max(0, total - (failed + errors))

        # Output summary line
        if total == 0:
            if "OK" in combined:
                summary = "Tests passed (uncounted output)"
                passed = 1
                total = 1
            else:
                summary = "No tests discovered or error occurred"
        else:
            summary = f"{passed}/{total} passed"
            if failed > 0:
                summary += f", {failed} failed"
            if errors > 0:
                summary += f", {errors} errors"

        return TestMetrics(
            total_tests=total,
            passed_tests=passed,
            failed_tests=failed,
            error_tests=errors,
            new_tests_added=0,  # calculated separately if test files changed
            execution_time=duration,
            output_summary=summary
        )

    def analyze(self, variation_name: str, sandbox_path: Path, test_res: Any, compilation_ok: bool = True, error: str = "") -> ImpactReport:
        """Run full impact analysis for a given sandbox."""
        file_metrics, raw_diff = self.compare_directories(self.base_repo, sandbox_path)
        dep_graph, in_degree = self.build_import_graph(sandbox_path)

        files_changed_count = len(file_metrics)
        total_added = sum(m.lines_added for m in file_metrics)
        total_deleted = sum(m.lines_deleted for m in file_metrics)
        critical_touched = [m.path for m in file_metrics if m.is_critical]

        # Calculate centrality impact: sum of in-degree of all changed modules
        centrality_score = 0.0
        for m in file_metrics:
            centrality_score += in_degree.get(m.path, 0)

        # Parse test metrics
        if test_res:
            test_metrics = self.parse_test_output(test_res.stdout, test_res.stderr, test_res.duration_seconds)
            if test_res.timed_out:
                test_metrics.failed_tests += 1
                test_metrics.output_summary = f"TIMED OUT ({test_metrics.output_summary})"
        else:
            test_metrics = TestMetrics(0, 0, 0, 0, 0, 0.0, "Tests skipped or failed to start")

        # Detect new test cases added
        for m in file_metrics:
            if "test" in m.path.lower() and m.lines_added > 0:
                test_metrics.new_tests_added += max(1, m.lines_added // 10)

        return ImpactReport(
            variation_name=variation_name,
            files_changed_count=files_changed_count,
            total_lines_added=total_added,
            total_lines_deleted=total_deleted,
            critical_files_touched=critical_touched,
            file_metrics=file_metrics,
            test_metrics=test_metrics,
            dependency_graph=dep_graph,
            module_centrality=in_degree,
            centrality_impact_score=centrality_score,
            raw_diff=raw_diff,
            compilation_ok=compilation_ok,
            error=error
        )
