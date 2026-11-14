"""Local Web UI server and dashboard renderer for ZeroG-Sandbox."""

from __future__ import annotations
import json
import os
import urllib.parse
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Any, Dict, List, Optional
from zerog_sandbox.config import load_config
from zerog_sandbox.impact_analyzer import ImpactAnalyzer
from zerog_sandbox.sandbox_manager import SandboxManager, VariationCandidate
from zerog_sandbox.scorer import GravityScorer, ScoredVariation
from zerog_sandbox.github_exporter import GitHubExporter


HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>ZeroG-Sandbox | Blast-Radius Simulator & Decision Engine</title>
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link href="https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;600;700&family=Plus+Jakarta+Sans:wght@400;500;600;700;800&display=swap" rel="stylesheet">
  <style>
    :root {
      --bg: #090d16;
      --card-bg: #111827;
      --card-border: #1f2937;
      --accent: #6366f1;
      --accent-glow: rgba(99, 102, 241, 0.25);
      --text: #f3f4f6;
      --text-muted: #9ca3af;
      --success: #10b981;
      --warning: #f59e0b;
      --danger: #ef4444;
      --font-sans: 'Plus Jakarta Sans', system-ui, sans-serif;
      --font-mono: 'JetBrains Mono', monospace;
    }
    * { box-sizing: border-box; margin: 0; padding: 0; }
    body {
      background: radial-gradient(circle at 50% 0%, #1e1b4b 0%, var(--bg) 60%);
      color: var(--text);
      font-family: var(--font-sans);
      min-height: 100vh;
      padding: 2rem 1.5rem;
    }
    .container { max-width: 1200px; margin: 0 auto; }
    header {
      display: flex;
      justify-content: space-between;
      align-items: center;
      margin-bottom: 2.5rem;
      padding-bottom: 1.5rem;
      border-bottom: 1px solid rgba(255,255,255,0.08);
    }
    .brand { display: flex; align-items: center; gap: 0.75rem; }
    .brand-icon {
      width: 42px;
      height: 42px;
      border-radius: 12px;
      background: linear-gradient(135deg, #6366f1, #a855f7);
      display: flex;
      align-items: center;
      justify-content: center;
      font-weight: 800;
      font-size: 1.25rem;
      box-shadow: 0 0 20px var(--accent-glow);
    }
    h1 { font-size: 1.6rem; font-weight: 800; letter-spacing: -0.02em; }
    .tagline { color: var(--text-muted); font-size: 0.85rem; margin-top: 0.2rem; }
    .status-badge {
      font-size: 0.75rem;
      background: rgba(99, 102, 241, 0.15);
      color: #818cf8;
      border: 1px solid rgba(99, 102, 241, 0.3);
      padding: 0.35rem 0.8rem;
      border-radius: 9999px;
      font-weight: 600;
      letter-spacing: 0.05em;
    }
    .actions-bar {
      display: flex;
      gap: 1rem;
      margin-bottom: 2rem;
      flex-wrap: wrap;
    }
    .btn {
      background: linear-gradient(135deg, #6366f1, #4f46e5);
      color: #fff;
      border: none;
      padding: 0.75rem 1.4rem;
      border-radius: 8px;
      font-weight: 600;
      font-size: 0.9rem;
      cursor: pointer;
      display: inline-flex;
      align-items: center;
      gap: 0.5rem;
      transition: all 0.2s;
      box-shadow: 0 4px 12px var(--accent-glow);
    }
    .btn:hover { transform: translateY(-1px); filter: brightness(1.1); }
    .btn-secondary {
      background: #1f2937;
      box-shadow: none;
      border: 1px solid #374151;
      color: var(--text);
    }
    .btn-secondary:hover { background: #374151; }
    .cards-grid {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(350px, 1fr));
      gap: 1.5rem;
      margin-bottom: 2.5rem;
    }
    .card {
      background: var(--card-bg);
      border: 1px solid var(--card-border);
      border-radius: 14px;
      padding: 1.5rem;
      display: flex;
      flex-direction: column;
      position: relative;
      transition: all 0.2s ease;
    }
    .card:hover { border-color: rgba(99, 102, 241, 0.4); box-shadow: 0 8px 30px rgba(0,0,0,0.4); }
    .card.recommended {
      border: 2px solid var(--success);
      box-shadow: 0 0 25px rgba(16, 185, 129, 0.2);
    }
    .rec-ribbon {
      position: absolute;
      top: -12px;
      right: 1.25rem;
      background: var(--success);
      color: #064e3b;
      font-size: 0.7rem;
      font-weight: 800;
      text-transform: uppercase;
      letter-spacing: 0.05em;
      padding: 0.25rem 0.6rem;
      border-radius: 6px;
    }
    .card-header {
      display: flex;
      justify-content: space-between;
      align-items: flex-start;
      margin-bottom: 1.25rem;
    }
    .card-title { font-size: 1.2rem; font-weight: 700; }
    .badge {
      font-size: 0.75rem;
      font-weight: 700;
      padding: 0.3rem 0.65rem;
      border-radius: 6px;
      text-transform: uppercase;
    }
    .badge-Light { background: rgba(16, 185, 129, 0.2); color: #34d399; border: 1px solid rgba(16, 185, 129, 0.3); }
    .badge-Medium { background: rgba(245, 158, 11, 0.2); color: #fbbf24; border: 1px solid rgba(245, 158, 11, 0.3); }
    .badge-Heavy { background: rgba(239, 68, 68, 0.2); color: #f87171; border: 1px solid rgba(239, 68, 68, 0.3); }
    .score-meter {
      margin-bottom: 1.25rem;
      background: rgba(0,0,0,0.3);
      padding: 1rem;
      border-radius: 10px;
      display: flex;
      align-items: baseline;
      justify-content: space-between;
    }
    .score-val { font-size: 2.2rem; font-family: var(--font-mono); font-weight: 800; }
    .score-lbl { font-size: 0.8rem; color: var(--text-muted); text-transform: uppercase; letter-spacing: 0.05em; }
    .metrics-list { list-style: none; margin-bottom: 1.5rem; font-size: 0.9rem; }
    .metrics-item {
      display: flex;
      justify-content: space-between;
      padding: 0.4rem 0;
      border-bottom: 1px solid rgba(255,255,255,0.05);
    }
    .metrics-item:last-child { border-bottom: none; }
    .val-danger { color: var(--danger); font-weight: 600; }
    .val-success { color: var(--success); font-weight: 600; }
    .val-mono { font-family: var(--font-mono); }
    .card-footer { margin-top: auto; padding-top: 1rem; display: flex; gap: 0.75rem; }
    .btn-land {
      flex: 1;
      background: #10b981;
      color: #064e3b;
      font-weight: 700;
      border: none;
      padding: 0.65rem;
      border-radius: 8px;
      cursor: pointer;
      transition: all 0.2s;
    }
    .btn-land:hover { background: #34d399; }
    .diff-section {
      background: var(--card-bg);
      border: 1px solid var(--card-border);
      border-radius: 14px;
      padding: 1.5rem;
      margin-top: 2rem;
    }
    .diff-header {
      display: flex;
      justify-content: space-between;
      align-items: center;
      margin-bottom: 1rem;
    }
    pre.code-diff {
      background: #05070c;
      border: 1px solid #1e293b;
      border-radius: 8px;
      padding: 1.25rem;
      font-family: var(--font-mono);
      font-size: 0.85rem;
      line-height: 1.5;
      overflow-x: auto;
      max-height: 400px;
      color: #cbd5e1;
    }
    .diff-add { color: #34d399; }
    .diff-del { color: #f87171; }
    .diff-meta { color: #818cf8; }
    .alert {
      padding: 0.75rem 1rem;
      border-radius: 8px;
      margin-bottom: 1.5rem;
      font-size: 0.9rem;
      display: flex;
      align-items: center;
      gap: 0.5rem;
    }
    .alert-danger { background: rgba(239, 68, 68, 0.15); border: 1px solid var(--danger); color: #fca5a5; }
    .alert-success { background: rgba(16, 185, 129, 0.15); border: 1px solid var(--success); color: #a7f3d0; }
  </style>
</head>
<body>
  <div class="container">
    <header>
      <div class="brand">
        <div class="brand-icon">&Delta;</div>
        <div>
          <h1>ZeroG-Sandbox</h1>
          <div class="tagline">Blast-Radius Simulator & Safe Landing Engine for GitHub</div>
        </div>
      </div>
      <div>
        <span class="status-badge" id="repoStatus">ACTIVE REPO: {{REPO_NAME}}</span>
      </div>
    </header>

    <div class="actions-bar">
      <button class="btn" onclick="runSimulation()">
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><polygon points="5 3 19 12 5 21 5 3"></polygon></svg>
        Re-Simulate All Variations
      </button>
      <button class="btn btn-secondary" onclick="exportWorkflow()">
        Generate GitHub Action
      </button>
    </div>

    <div id="alertBox"></div>

    <main>
      <h2 style="font-size: 1.25rem; margin-bottom: 1.25rem; font-weight: 700;">Candidate Variations Impact Comparison</h2>
      <div class="cards-grid" id="cardsGrid">
        <!-- Rendered via JS -->
      </div>

      <section class="diff-section" id="diffSection" style="display:none;">
        <div class="diff-header">
          <h3 id="diffTitle" style="font-size: 1.1rem; font-weight: 700;">Unified Diff Inspector</h3>
          <span id="diffFilesCount" style="color:var(--text-muted); font-size:0.85rem;"></span>
        </div>
        <pre class="code-diff" id="diffCode"></pre>
      </section>
    </main>
  </div>

  <script>
    let currentVariations = [];

    async function loadData() {
      try {
        const res = await fetch('/api/variations');
        const data = await res.json();
        currentVariations = data.variations || [];
        renderCards(currentVariations);
      } catch (err) {
        showAlert('Failed to connect to ZeroG local backend: ' + err, 'danger');
      }
    }

    function renderCards(variations) {
      const grid = document.getElementById('cardsGrid');
      grid.innerHTML = '';

      if (variations.length === 0) {
        grid.innerHTML = '<div style="grid-column: 1/-1; padding: 2rem; background: var(--card-bg); border-radius: 12px; text-align: center; color: var(--text-muted);">No candidate variations found. Add candidate directories or patches in your repo.</div>';
        return;
      }

      variations.forEach(v => {
        const card = document.createElement('div');
        card.className = 'card' + (v.is_recommended ? ' recommended' : '');
        
        let recBadge = v.is_recommended ? '<div class="rec-ribbon">&star; Recommended Choice</div>' : '';
        let warnBox = v.warning_message ? `<div style="background:rgba(239,68,68,0.15); color:#fca5a5; font-size:0.8rem; padding:0.4rem 0.6rem; border-radius:6px; margin-bottom:0.75rem;">&bull; ${v.warning_message}</div>` : '';

        card.innerHTML = `
          ${recBadge}
          <div class="card-header">
            <div>
              <div class="card-title">${v.variation_name}</div>
              <div style="font-size:0.8rem; color:var(--text-muted); margin-top:2px;">${v.report.test_metrics.output_summary}</div>
            </div>
            <span class="badge badge-${v.badge}">${v.badge}</span>
          </div>

          <div class="score-meter">
            <div>
              <span class="score-lbl">Blast-Radius Score</span>
              <div class="score-val" style="color:${v.badge_color}">${v.score}</div>
            </div>
            <div style="text-align:right;">
              <div style="font-size:0.8rem; color:var(--text-muted);">Execution Time</div>
              <div class="val-mono" style="font-weight:700;">${v.execution_time}s</div>
            </div>
          </div>

          ${warnBox}

          <ul class="metrics-list">
            <li class="metrics-item">
              <span>Files Touched</span>
              <span class="val-mono">${v.files_changed}</span>
            </li>
            <li class="metrics-item">
              <span>Lines Delta</span>
              <span class="val-mono"><span style="color:#34d399;">+${v.lines_added}</span> / <span style="color:#f87171;">-${v.lines_deleted}</span></span>
            </li>
            <li class="metrics-item">
              <span>Critical Files Touched</span>
              <span class="val-mono ${v.critical_files_touched.length > 0 ? 'val-danger' : 'val-success'}">
                ${v.critical_files_touched.length > 0 ? v.critical_files_touched.join(', ') : 'None (Safe)'}
              </span>
            </li>
            <li class="metrics-item">
              <span>Broken / Failed Tests</span>
              <span class="val-mono ${v.has_broken_tests ? 'val-danger' : 'val-success'}">${v.broken_test_count}</span>
            </li>
          </ul>

          <div class="card-footer">
            <button class="btn btn-secondary" style="font-size:0.85rem;" onclick="viewDiff('${v.variation_name}')">Inspect Diff</button>
            <button class="btn-land" onclick="landVariation('${v.variation_name}')">Land to Branch</button>
          </div>
        `;
        grid.appendChild(card);
      });
    }

    function viewDiff(name) {
      const v = currentVariations.find(item => item.variation_name === name);
      if (!v) return;

      const sec = document.getElementById('diffSection');
      const title = document.getElementById('diffTitle');
      const filesCount = document.getElementById('diffFilesCount');
      const code = document.getElementById('diffCode');

      sec.style.display = 'block';
      title.innerText = `Diff Inspector: ${v.variation_name}`;
      filesCount.innerText = `${v.files_changed} files changed (+${v.lines_added} / -${v.lines_deleted})`;

      const formatted = (v.report.raw_diff || 'No diff detected (identical files)').split('\\n').map(line => {
        if (line.startsWith('+') && !line.startsWith('+++')) return `<span class="diff-add">${escapeHtml(line)}</span>`;
        if (line.startsWith('-') && !line.startsWith('---')) return `<span class="diff-del">${escapeHtml(line)}</span>`;
        if (line.startsWith('@@') || line.startsWith('---') || line.startsWith('+++')) return `<span class="diff-meta">${escapeHtml(line)}</span>`;
        return escapeHtml(line);
      }).join('\\n');

      code.innerHTML = formatted;
      sec.scrollIntoView({ behavior: 'smooth' });
    }

    async function landVariation(name) {
      if (!confirm(`Are you sure you want to Land '${name}' directly into a git branch and prepare GitHub PR?`)) return;
      try {
        const res = await fetch('/api/land', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ variation_name: name })
        });
        const result = await res.json();
        if (result.success) {
          showAlert(result.message, 'success');
        } else {
          showAlert(result.message, 'danger');
        }
      } catch (err) {
        showAlert('Error landing variation: ' + err, 'danger');
      }
    }

    async function runSimulation() {
      showAlert('Simulating all variations in isolated sandboxes...', 'success');
      try {
        const res = await fetch('/api/simulate', { method: 'POST' });
        const data = await res.json();
        currentVariations = data.variations || [];
        renderCards(currentVariations);
        showAlert('Simulation completed successfully!', 'success');
      } catch (err) {
        showAlert('Simulation failed: ' + err, 'danger');
      }
    }

    async function exportWorkflow() {
      try {
        const res = await fetch('/api/workflow', { method: 'POST' });
        const data = await res.json();
        showAlert(data.message, 'success');
      } catch (err) {
        showAlert('Failed to export workflow: ' + err, 'danger');
      }
    }

    function showAlert(msg, type) {
      const box = document.getElementById('alertBox');
      box.innerHTML = `<div class="alert alert-${type}">${escapeHtml(msg)}</div>`;
      setTimeout(() => { box.innerHTML = ''; }, 7000);
    }

    function escapeHtml(str) {
      return str.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
    }

    loadData();
  </script>
</body>
</html>
"""


class ZeroGServer:
    def __init__(self, repo_dir: Path | str, candidates: List[VariationCandidate], port: int = 8484):
        self.repo_dir = Path(repo_dir).resolve()
        self.candidates = candidates
        self.port = port
        self.config = load_config(self.repo_dir)
        self.scorer = GravityScorer(self.config["weights"], self.config["score_thresholds"])
        self.analyzer = ImpactAnalyzer(self.repo_dir, self.config["critical_files"], self.config["ignore_patterns"])
        self.cached_results: List[ScoredVariation] = []

    def run_simulation(self) -> List[ScoredVariation]:
        mgr = SandboxManager(self.repo_dir, self.config["ignore_patterns"])
        reports = []
        for cand in self.candidates:
            sandbox = mgr.create_sandbox()
            err_msg = ""
            comp_ok = True
            try:
                mgr.apply_variation(sandbox, cand)
            except Exception as e:
                err_msg = str(e)
                comp_ok = False

            test_res = None
            if comp_ok and self.config.get("test_command"):
                test_res = mgr.run_command(sandbox, self.config["test_command"], timeout_seconds=self.config.get("timeout_seconds", 30))
                if test_res.exit_code != 0 and not test_res.stdout and not test_res.stderr:
                    comp_ok = False

            rep = self.analyzer.analyze(cand.name, sandbox, test_res, compilation_ok=comp_ok, error=err_msg)
            reports.append(rep)
            mgr.clean_sandbox(sandbox)

        self.cached_results = self.scorer.rank_variations(reports)
        return self.cached_results

    def start(self, open_browser: bool = False):
        self.run_simulation()
        outer = self

        class RequestHandler(BaseHTTPRequestHandler):
            def do_GET(self):
                if self.path == "/" or self.path.startswith("/?"):
                    html = HTML_TEMPLATE.replace("{{REPO_NAME}}", outer.repo_dir.name)
                    self.send_response(200)
                    self.send_header("Content-Type", "text/html; charset=utf-8")
                    self.end_headers()
                    self.wfile.write(html.encode("utf-8"))
                elif self.path == "/api/variations":
                    self.send_response(200)
                    self.send_header("Content-Type", "application/json")
                    self.end_headers()
                    data = [outer._variation_to_dict(v) for v in outer.cached_results]
                    self.wfile.write(json.dumps({"variations": data}).encode("utf-8"))
                else:
                    self.send_response(404)
                    self.end_headers()

            def do_POST(self):
                if self.path == "/api/simulate":
                    res = outer.run_simulation()
                    self.send_response(200)
                    self.send_header("Content-Type", "application/json")
                    self.end_headers()
                    data = [outer._variation_to_dict(v) for v in res]
                    self.wfile.write(json.dumps({"variations": data}).encode("utf-8"))
                elif self.path == "/api/workflow":
                    exporter = GitHubExporter(outer.repo_dir)
                    target = exporter.generate_workflow_template()
                    self.send_response(200)
                    self.send_header("Content-Type", "application/json")
                    self.end_headers()
                    self.wfile.write(json.dumps({"message": f"Generated {target.name} under .github/workflows/"}).encode("utf-8"))
                elif self.path == "/api/land":
                    length = int(self.headers.get("content-length", 0))
                    body = self.rfile.read(length).decode("utf-8")
                    params = json.loads(body)
                    v_name = params.get("variation_name")
                    cand = next((c for c in outer.candidates if c.name == v_name), None)
                    if not cand:
                        self.send_response(404)
                        self.end_headers()
                        self.wfile.write(json.dumps({"success": False, "message": "Variation not found"}).encode("utf-8"))
                        return

                    exporter = GitHubExporter(outer.repo_dir)
                    branch_name = f"zerog/{cand.name.lower().replace(' ', '-')}"
                    land_res = exporter.land_variation(
                        cand,
                        branch_name=branch_name,
                        commit_message=f"feat(zerog): apply {cand.name} (Blast-Radius verified)",
                        create_pr=True
                    )
                    self.send_response(200)
                    self.send_header("Content-Type", "application/json")
                    self.end_headers()
                    self.wfile.write(json.dumps({
                        "success": land_res.success,
                        "branch_name": land_res.branch_name,
                        "message": land_res.message,
                        "pr_url": land_res.pr_url
                    }).encode("utf-8"))
                else:
                    self.send_response(404)
                    self.end_headers()

            def log_message(self, format, *args):
                pass  # Keep server output quiet

        server = HTTPServer(("127.0.0.1", self.port), RequestHandler)
        print(f"\n[ZeroG Web UI] Running locally at: http://127.0.0.1:{self.port}")
        if open_browser:
            import webbrowser
            webbrowser.open(f"http://127.0.0.1:{self.port}")
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            server.server_close()
            print("\n[ZeroG Web UI] Server stopped.")

    def _variation_to_dict(self, v: ScoredVariation) -> Dict[str, Any]:
        return {
            "variation_name": v.variation_name,
            "score": v.score,
            "badge": v.badge,
            "badge_color": v.badge_color,
            "has_broken_tests": v.has_broken_tests,
            "broken_test_count": v.broken_test_count,
            "critical_files_touched": v.critical_files_touched,
            "files_changed": v.files_changed,
            "lines_added": v.lines_added,
            "lines_deleted": v.lines_deleted,
            "execution_time": v.execution_time,
            "breakdown": v.breakdown,
            "is_recommended": v.is_recommended,
            "warning_message": v.warning_message,
            "report": {
                "raw_diff": v.report.raw_diff,
                "test_metrics": {
                    "total_tests": v.report.test_metrics.total_tests,
                    "passed_tests": v.report.test_metrics.passed_tests,
                    "failed_tests": v.report.test_metrics.failed_tests,
                    "error_tests": v.report.test_metrics.error_tests,
                    "output_summary": v.report.test_metrics.output_summary
                }
            }
        }
