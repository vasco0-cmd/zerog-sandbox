"""Scorer: Calculates Blast-Radius / Gravity Score, ranks variations, and generates impact labels."""

from __future__ import annotations
from dataclasses import dataclass
from typing import Any, Dict, List
from zerog_sandbox.impact_analyzer import ImpactReport


@dataclass
class ScoredVariation:
    variation_name: str
    score: float
    badge: str  # "Light", "Medium", "Heavy"
    badge_color: str  # "green", "amber", "red"
    has_broken_tests: bool
    broken_test_count: int
    critical_files_touched: List[str]
    files_changed: int
    lines_added: int
    lines_deleted: int
    execution_time: float
    breakdown: Dict[str, float]
    report: ImpactReport
    is_recommended: bool = False
    warning_message: str = ""


class GravityScorer:
    """Computes the Blast-Radius Score for candidate solutions."""

    def __init__(self, weights: Dict[str, float], thresholds: Dict[str, float]):
        self.weights = weights
        self.thresholds = thresholds

    def score_variation(self, report: ImpactReport) -> ScoredVariation:
        w = self.weights

        file_penalty = report.files_changed_count * w.get("files_changed", 4.0)
        lines_add_penalty = report.total_lines_added * w.get("lines_added", 0.2)
        lines_del_penalty = report.total_lines_deleted * w.get("lines_deleted", 0.3)
        crit_penalty = len(report.critical_files_touched) * w.get("critical_file_hit", 25.0)
        dep_penalty = report.centrality_impact_score * w.get("dependency_centrality_factor", 6.0)

        broken_tests = report.test_metrics.failed_tests + report.test_metrics.error_tests
        has_broken = broken_tests > 0 or not report.compilation_ok or bool(report.error)
        test_penalty = broken_tests * w.get("broken_test_penalty", 50.0)

        if not report.compilation_ok:
            test_penalty += 75.0
        if report.error:
            test_penalty += 100.0

        time_penalty = report.test_metrics.execution_time * w.get("execution_time_factor", 0.5)

        # Bonus for adding clean new tests without breaking anything
        test_bonus = 0.0
        if not has_broken and report.test_metrics.new_tests_added > 0:
            test_bonus = min(15.0, report.test_metrics.new_tests_added * 2.5)

        total_score = max(0.0, (
            file_penalty +
            lines_add_penalty +
            lines_del_penalty +
            crit_penalty +
            dep_penalty +
            test_penalty +
            time_penalty -
            test_bonus
        ))
        total_score = round(total_score, 1)

        # Determine badge: Light, Medium, Heavy
        light_max = self.thresholds.get("light_max", 25.0)
        medium_max = self.thresholds.get("medium_max", 65.0)

        if total_score <= light_max and not has_broken:
            badge = "Light"
            badge_color = "#10b981"  # emerald green
        elif total_score <= medium_max and not has_broken:
            badge = "Medium"
            badge_color = "#f59e0b"  # amber
        else:
            badge = "Heavy"
            badge_color = "#ef4444"  # red

        warning_message = ""
        if has_broken:
            if not report.compilation_ok:
                warning_message = "Compilation/Build failure detected!"
            elif report.error:
                warning_message = f"Error in variation: {report.error}"
            else:
                warning_message = f"{broken_tests} test(s) failed!"

        breakdown = {
            "files": round(file_penalty, 1),
            "lines_added": round(lines_add_penalty, 1),
            "lines_deleted": round(lines_del_penalty, 1),
            "critical_modules": round(crit_penalty, 1),
            "dependency_centrality": round(dep_penalty, 1),
            "test_failures": round(test_penalty, 1),
            "execution_time": round(time_penalty, 1),
            "test_coverage_bonus": round(-test_bonus, 1)
        }

        return ScoredVariation(
            variation_name=report.variation_name,
            score=total_score,
            badge=badge,
            badge_color=badge_color,
            has_broken_tests=has_broken,
            broken_test_count=broken_tests,
            critical_files_touched=report.critical_files_touched,
            files_changed=report.files_changed_count,
            lines_added=report.total_lines_added,
            lines_deleted=report.total_lines_deleted,
            execution_time=report.test_metrics.execution_time,
            breakdown=breakdown,
            report=report,
            warning_message=warning_message
        )

    def rank_variations(self, reports: List[ImpactReport]) -> List[ScoredVariation]:
        """Ranks variations from lowest blast-radius to highest."""
        scored = [self.score_variation(r) for r in reports]

        # Sorting key: variations without broken tests are strongly preferred; then lower score wins
        scored.sort(key=lambda s: (1 if s.has_broken_tests else 0, s.score))

        if scored and not scored[0].has_broken_tests:
            scored[0].is_recommended = True

        return scored
