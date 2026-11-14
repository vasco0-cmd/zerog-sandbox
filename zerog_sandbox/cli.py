"""Command-line Interface for ZeroG-Sandbox."""

from __future__ import annotations
import argparse
import json
import os
import sys
from pathlib import Path
from typing import List, Optional
from zerog_sandbox.config import DEFAULT_CONFIG, load_config
from zerog_sandbox.impact_analyzer import ImpactAnalyzer
from zerog_sandbox.sandbox_manager import SandboxManager, VariationCandidate
from zerog_sandbox.scorer import GravityScorer, ScoredVariation
from zerog_sandbox.github_exporter import GitHubExporter
from zerog_sandbox.web_ui import ZeroGServer


def discover_candidates(repo_dir: Path, explicit_candidates: Optional[List[str]] = None) -> List[VariationCandidate]:
    """Auto-detect candidate variations from candidates/ directory, patches, or arguments."""
    candidates: List[VariationCandidate] = []

    if explicit_candidates:
        for item in explicit_candidates:
            p = Path(item).resolve()
            if p.is_dir():
                candidates.append(VariationCandidate(name=p.name, source_type="dir", source_path=str(p)))
            elif p.is_file() and p.suffix in (".patch", ".diff"):
                candidates.append(VariationCandidate(name=p.stem, source_type="patch", source_path=str(p)))
            elif p.is_file() and p.suffix in (".py", ".sh", ".bat"):
                candidates.append(VariationCandidate(name=p.stem, source_type="script", source_path=str(p)))
            else:
                print(f"[WARN] Unknown candidate path: {item}")
        return candidates

    # Auto-discovery in repo_dir/candidates or variations
    search_dirs = [
        repo_dir / "candidates",
        repo_dir / "variations",
        repo_dir / "patches"
    ]

    for s_dir in search_dirs:
        if s_dir.is_dir():
            for child in sorted(s_dir.iterdir()):
                if child.is_dir() and not child.name.startswith("."):
                    candidates.append(VariationCandidate(name=child.name, source_type="dir", source_path=str(child)))
                elif child.is_file() and child.suffix in (".patch", ".diff"):
                    candidates.append(VariationCandidate(name=child.stem, source_type="patch", source_path=str(child)))
                elif child.is_file() and child.suffix in (".py",):
                    candidates.append(VariationCandidate(name=child.stem, source_type="script", source_path=str(child)))

    return candidates


def print_comparison_table(scored_variations: List[ScoredVariation]):
    """Pretty prints terminal comparison table with gravity scores and blast-radiuses."""
    print("\n" + "=" * 84)
    print("                ZEROG-SANDBOX | BLAST-RADIUS IMPACT COMPARISON              ")
    print("=" * 84)
    header = f"{'Variation':<18} | {'Score':<8} | {'Badge':<8} | {'Delta Lines':<14} | {'Tests':<12} | {'Crit?':<6}"
    print(header)
    print("-" * 84)

    for v in scored_variations:
        delta_str = f"+{v.lines_added} / -{v.lines_deleted}"
        test_str = "FAILED" if v.has_broken_tests else "PASSED"
        crit_str = "YES" if v.critical_files_touched else "SAFE"
        rec_marker = " [★ RECOMMENDED]" if v.is_recommended else ""
        row = f"{v.variation_name:<18} | {v.score:<8.1f} | {v.badge:<8} | {delta_str:<14} | {test_str:<12} | {crit_str:<6}{rec_marker}"
        print(row)

    print("=" * 84)

    # Detailed warnings
    broken_count = sum(1 for v in scored_variations if v.has_broken_tests)
    if broken_count == len(scored_variations) and broken_count > 0:
        print("\n[ALERT] ALL variations have broken tests or errors! Review details carefully.")
    elif broken_count > 0:
        print(f"\n[NOTE] {broken_count} variation(s) broke existing tests and were penalized.")


def run_simulation_pipeline(repo_dir: Path, candidates: List[VariationCandidate]) -> List[ScoredVariation]:
    config = load_config(repo_dir)
    mgr = SandboxManager(repo_dir, config["ignore_patterns"])
    analyzer = ImpactAnalyzer(repo_dir, config["critical_files"], config["ignore_patterns"])
    scorer = GravityScorer(config["weights"], config["score_thresholds"])

    reports = []
    for cand in candidates:
        sandbox = mgr.create_sandbox()
        err = ""
        comp_ok = True
        try:
            mgr.apply_variation(sandbox, cand)
        except Exception as e:
            err = str(e)
            comp_ok = False

        test_res = None
        if comp_ok and config.get("test_command"):
            test_res = mgr.run_command(sandbox, config["test_command"], timeout_seconds=config.get("timeout_seconds", 30))
            if test_res.exit_code != 0 and not test_res.stdout and not test_res.stderr:
                comp_ok = False

        rep = analyzer.analyze(cand.name, sandbox, test_res, compilation_ok=comp_ok, error=err)
        reports.append(rep)
        mgr.clean_sandbox(sandbox)

    return scorer.rank_variations(reports)


def main():
    parser = argparse.ArgumentParser(
        prog="zerog",
        description="ZeroG-Sandbox: Blast-radius simulator and safe landing engine for GitHub."
    )
    subparsers = parser.add_subparsers(dest="command", help="Sub-commands")

    # Command: init-config
    p_init = subparsers.add_parser("init-config", help="Initialize zerog.json configuration in repo")
    p_init.add_argument("--repo", default=".", help="Repository root directory")

    # Command: simulate
    p_sim = subparsers.add_parser("simulate", help="Simulate a single patch or directory change in isolated sandbox")
    p_sim.add_argument("--repo", default=".", help="Repository root directory")
    p_sim.add_argument("--target", required=False, help="Patch file or directory to simulate")
    p_sim.add_argument("--threshold", type=float, default=None, help="Fail exit code if score exceeds threshold")

    # Command: compare
    p_comp = subparsers.add_parser("compare", help="Compare multiple variations side-by-side and rank them")
    p_comp.add_argument("--repo", default=".", help="Repository root directory")
    p_comp.add_argument("candidates", nargs="*", help="List of candidate directories, patches, or scripts")

    # Command: land
    p_land = subparsers.add_parser("land", help="Land best or chosen variation onto a clean git branch & PR")
    p_land.add_argument("--repo", default=".", help="Repository root directory")
    p_land.add_argument("--variation", required=False, help="Name or path of variation to land (default: auto best)")
    p_land.add_argument("--branch", default=None, help="Custom branch name")
    p_land.add_argument("--pr", action="store_true", help="Attempt GitHub PR creation via gh CLI")

    # Command: ui
    p_ui = subparsers.add_parser("ui", help="Launch interactive local Web UI")
    p_ui.add_argument("--repo", default=".", help="Repository root directory")
    p_ui.add_argument("--port", type=int, default=8484, help="Port for local server")
    p_ui.add_argument("--no-browser", action="store_true", help="Do not automatically launch browser")

    args = parser.parse_args()
    if not args.command:
        parser.print_help()
        sys.exit(0)

    repo_dir = Path(getattr(args, "repo", ".")).resolve()

    if args.command == "init-config":
        cfg_path = repo_dir / "zerog.json"
        if cfg_path.exists():
            print(f"[INFO] Configuration file already exists at {cfg_path}")
        else:
            cfg_path.write_text(json.dumps(DEFAULT_CONFIG, indent=2), encoding="utf-8")
            print(f"[SUCCESS] Created default configuration at {cfg_path}")

    elif args.command == "compare":
        candidates = discover_candidates(repo_dir, args.candidates if args.candidates else None)
        if not candidates:
            print("[ERROR] No candidate variations found. Specify candidates or add them to 'candidates/' directory.")
            sys.exit(1)

        print(f"[ZeroG] Simulating {len(candidates)} candidate variations...")
        results = run_simulation_pipeline(repo_dir, candidates)
        print_comparison_table(results)

    elif args.command == "simulate":
        targets = [args.target] if args.target else None
        candidates = discover_candidates(repo_dir, targets)
        if not candidates:
            print("[ERROR] No target specified or found to simulate.")
            sys.exit(1)

        results = run_simulation_pipeline(repo_dir, candidates)
        print_comparison_table(results)

        if args.threshold is not None:
            best = results[0]
            if best.score > args.threshold or best.has_broken_tests:
                print(f"\n[FAIL] Score {best.score} exceeds threshold {args.threshold} or tests failed!")
                sys.exit(2)
            else:
                print(f"\n[PASS] Score {best.score} is within threshold {args.threshold}.")

    elif args.command == "land":
        candidates = discover_candidates(repo_dir)
        if not candidates:
            print("[ERROR] No candidates found to land.")
            sys.exit(1)

        results = run_simulation_pipeline(repo_dir, candidates)
        target_name = args.variation
        selected = None
        if target_name:
            selected = next((c for c in candidates if c.name == target_name), None)
        else:
            # Pick best recommended
            valid = [r for r in results if not r.has_broken_tests]
            best_r = valid[0] if valid else results[0]
            selected = next((c for c in candidates if c.name == best_r.variation_name), None)

        if not selected:
            print(f"[ERROR] Could not resolve candidate variation to land.")
            sys.exit(1)

        branch_name = args.branch or f"zerog/{selected.name.lower().replace(' ', '-')}"
        exporter = GitHubExporter(repo_dir)
        res = exporter.land_variation(
            selected,
            branch_name=branch_name,
            commit_message=f"feat(zerog): land variation {selected.name} (Blast-Radius verified)",
            create_pr=args.pr
        )
        print("\n" + res.message)
        if not res.success:
            sys.exit(1)

    elif args.command == "ui":
        candidates = discover_candidates(repo_dir)
        server = ZeroGServer(repo_dir, candidates, port=args.port)
        server.start(open_browser=not args.no_browser)


if __name__ == "__main__":
    main()
