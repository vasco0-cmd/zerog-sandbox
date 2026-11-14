"""Unit and integration tests for ZeroG-Sandbox core modules."""

import os
import shutil
import tempfile
import unittest
from pathlib import Path
from zerog_sandbox.config import DEFAULT_CONFIG, load_config
from zerog_sandbox.sandbox_manager import SandboxManager, VariationCandidate
from zerog_sandbox.impact_analyzer import ImpactAnalyzer
from zerog_sandbox.scorer import GravityScorer
from zerog_sandbox.github_exporter import GitHubExporter


class TestZeroGSandbox(unittest.TestCase):
    def setUp(self):
        self.test_dir = Path(tempfile.mkdtemp(prefix="zerog_unit_test_")).resolve()
        # Create a mini mock repository
        self.auth_file = self.test_dir / "auth.py"
        self.auth_file.write_text("def auth(): return True\n", encoding="utf-8")
        
        self.app_file = self.test_dir / "app.py"
        self.app_file.write_text("import auth\ndef run(): return auth.auth()\n", encoding="utf-8")
        
        self.test_script = self.test_dir / "test_app.py"
        self.test_script.write_text(
            "import unittest\nimport app\nclass TestApp(unittest.TestCase):\n"
            "    def test_run(self): self.assertTrue(app.run())\n"
            "if __name__ == '__main__': unittest.main()\n",
            encoding="utf-8"
        )

    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_config_loading_and_fallback(self):
        cfg = load_config(self.test_dir)
        self.assertIn("weights", cfg)
        self.assertEqual(cfg["timeout_seconds"], 30)

        # Write custom config
        custom = self.test_dir / "zerog.json"
        custom.write_text('{"timeout_seconds": 99, "critical_files": ["secret.py"]}', encoding="utf-8")
        cfg2 = load_config(self.test_dir)
        self.assertEqual(cfg2["timeout_seconds"], 99)
        self.assertEqual(cfg2["critical_files"], ["secret.py"])

    def test_sandbox_manager_lifecycle_and_timeout(self):
        mgr = SandboxManager(self.test_dir)
        sandbox = mgr.create_sandbox()
        self.assertTrue(sandbox.exists())
        self.assertTrue((sandbox / "auth.py").exists())

        # Test safe execution
        res = mgr.run_command(sandbox, 'py -c "print(42)"')
        self.assertEqual(res.exit_code, 0)
        self.assertIn("42", res.stdout)

        # Test timeout handling
        res_timeout = mgr.run_command(sandbox, 'py -c "import time; time.sleep(5)"', timeout_seconds=1)
        self.assertTrue(res_timeout.timed_out)

        # Clean sandbox
        mgr.clean_sandbox(sandbox)
        self.assertFalse(sandbox.exists())

    def test_impact_analyzer_and_dependency_graph(self):
        mgr = SandboxManager(self.test_dir)
        sandbox = mgr.create_sandbox()

        # Modify app.py in sandbox
        app_copy = sandbox / "app.py"
        app_copy.write_text("import auth\ndef run(): return False\n", encoding="utf-8")

        analyzer = ImpactAnalyzer(self.test_dir, critical_files=["auth.py"], ignore_patterns=[])
        dep_graph, in_degree = analyzer.build_import_graph(sandbox)

        self.assertIn("auth.py", in_degree)
        self.assertGreaterEqual(in_degree["auth.py"], 1)

        rep = analyzer.analyze("variation_test", sandbox, None)
        self.assertEqual(rep.files_changed_count, 1)
        self.assertFalse(rep.critical_files_touched)  # app.py is not critical

        mgr.clean_sandbox(sandbox)

    def test_scorer_ranking_and_penalty(self):
        analyzer = ImpactAnalyzer(self.test_dir, critical_files=["auth.py"], ignore_patterns=[])
        scorer = GravityScorer(DEFAULT_CONFIG["weights"], DEFAULT_CONFIG["score_thresholds"])

        # Light variation
        sb_light = SandboxManager(self.test_dir).create_sandbox()
        (sb_light / "app.py").write_text("# comment\nimport auth\ndef run(): return auth.auth()\n", encoding="utf-8")
        test_ok = SandboxManager(self.test_dir).run_command(sb_light, f'py "{sb_light / "test_app.py"}"')
        rep_light = analyzer.analyze("light", sb_light, test_ok)

        # Broken variation
        sb_broken = SandboxManager(self.test_dir).create_sandbox()
        (sb_broken / "app.py").write_text("import auth\ndef run(): return False\n", encoding="utf-8")
        test_fail = SandboxManager(self.test_dir).run_command(sb_broken, f'py "{sb_broken / "test_app.py"}"')
        rep_broken = analyzer.analyze("broken", sb_broken, test_fail)

        ranked = scorer.rank_variations([rep_broken, rep_light])
        self.assertEqual(ranked[0].variation_name, "light")
        self.assertTrue(ranked[0].is_recommended)
        self.assertTrue(ranked[1].has_broken_tests)
        self.assertEqual(ranked[1].badge, "Heavy")

        SandboxManager(self.test_dir).clean_sandbox(sb_light)
        SandboxManager(self.test_dir).clean_sandbox(sb_broken)

    def test_github_workflow_generation(self):
        exporter = GitHubExporter(self.test_dir)
        wf_path = exporter.generate_workflow_template()
        self.assertTrue(wf_path.exists())
        content = wf_path.read_text(encoding="utf-8")
        self.assertIn("ZeroG Blast-Radius Verification", content)


if __name__ == "__main__":
    unittest.main()
