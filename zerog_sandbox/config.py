"""Configuration reader and defaults for ZeroG-Sandbox."""

from __future__ import annotations
import json
import os
from pathlib import Path
from typing import Any, Dict, List, Optional


DEFAULT_CONFIG: Dict[str, Any] = {
    "project_name": "ZeroG-Project",
    "test_command": "py -m unittest discover -s tests -p \"test_*.py\"",
    "build_command": "",
    "timeout_seconds": 30,
    "critical_files": [
        "auth.py",
        "security.py",
        "database.py",
        "db.py",
        "config.py",
        "core.py",
        "models.py"
    ],
    "ignore_patterns": [
        ".git",
        ".git/*",
        "*/.git/*",
        "__pycache__",
        "*.pyc",
        "*.pyo",
        ".pytest_cache",
        ".venv",
        "venv",
        "node_modules",
        ".zerog_cache",
        "candidates",
        "candidates/*",
        "variations",
        "variations/*",
        "patches",
        "patches/*"
    ],
    "weights": {
        "files_changed": 4.0,
        "lines_added": 0.2,
        "lines_deleted": 0.3,
        "critical_file_hit": 25.0,
        "broken_test_penalty": 50.0,
        "execution_time_factor": 0.5,
        "dependency_centrality_factor": 6.0
    },
    "score_thresholds": {
        "light_max": 25.0,
        "medium_max": 65.0
    }
}


def find_config_file(repo_dir: Path | str) -> Optional[Path]:
    repo_path = Path(repo_dir).resolve()
    candidates = [
        repo_path / "zerog.json",
        repo_path / "zerog.yml",
        repo_path / "zerog.yaml",
        repo_path / ".zerog.json",
        repo_path / ".zerog.yml"
    ]
    for c in candidates:
        if c.is_file():
            return c
    return None


def parse_simple_yaml(text: str) -> Dict[str, Any]:
    """Lightweight zero-dependency parser for flat/simple YAML files."""
    data: Dict[str, Any] = {}
    current_key = None
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if ":" in line and not line.strip().startswith("-"):
            parts = line.split(":", 1)
            key = parts[0].strip()
            val = parts[1].strip()
            if not val:
                current_key = key
                data[current_key] = []
            else:
                current_key = None
                # Clean quotes and basic types
                if val.lower() in ("true", "false"):
                    data[key] = (val.lower() == "true")
                elif val.isdigit():
                    data[key] = int(val)
                else:
                    try:
                        data[key] = float(val)
                    except ValueError:
                        data[key] = val.strip("'\"")
        elif stripped.startswith("- ") and current_key:
            item = stripped[2:].strip().strip("'\"")
            if isinstance(data.get(current_key), list):
                data[current_key].append(item)
    return data


def load_config(repo_dir: Path | str) -> Dict[str, Any]:
    config = json.loads(json.dumps(DEFAULT_CONFIG))  # deep copy
    cfg_file = find_config_file(repo_dir)
    if not cfg_file:
        return config

    try:
        content = cfg_file.read_text(encoding="utf-8")
        if cfg_file.suffix in (".json",):
            user_data = json.loads(content)
        else:
            user_data = parse_simple_yaml(content)

        # Merge configs recursively for nested dicts
        for k, v in user_data.items():
            if isinstance(v, dict) and k in config and isinstance(config[k], dict):
                config[k].update(v)
            else:
                config[k] = v
    except Exception as e:
        print(f"[WARN] Failed to parse config {cfg_file}: {e}. Using defaults.")

    return config
