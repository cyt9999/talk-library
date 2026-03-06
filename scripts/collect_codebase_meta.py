#!/usr/bin/env python3
"""Collect codebase metadata for architecture doc generation."""

import glob
import json
import os
import re
import sys

ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))


def count_lines(filepath):
    """Count non-empty lines in a file."""
    try:
        with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
            return sum(1 for line in f if line.strip())
    except Exception:
        return 0


def count_files(directory, pattern="*"):
    """Count files matching pattern in directory."""
    path = os.path.join(ROOT_DIR, directory)
    if not os.path.isdir(path):
        return 0
    return len(glob.glob(os.path.join(path, pattern)))


def parse_requirements(filepath):
    """Parse requirements.txt into list of {name, version_spec}."""
    deps = []
    try:
        with open(filepath, "r") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#"):
                    match = re.match(r"([a-zA-Z0-9_-]+)(.*)", line)
                    if match:
                        deps.append({"name": match.group(1), "version": match.group(2).strip()})
    except FileNotFoundError:
        pass
    return deps


def parse_workflow(filepath):
    """Extract key info from a GitHub Actions YAML file."""
    info = {"name": "", "triggers": [], "env_vars": [], "steps": []}
    try:
        with open(filepath, "r") as f:
            content = f.read()
        m = re.search(r"^name:\s*(.+)$", content, re.MULTILINE)
        if m:
            info["name"] = m.group(1).strip()
        for trigger in ["schedule", "workflow_dispatch", "workflow_run", "push"]:
            if trigger in content:
                info["triggers"].append(trigger)
        for m in re.finditer(r"secrets\.([A-Z_]+)", content):
            var = m.group(1)
            if var not in info["env_vars"]:
                info["env_vars"].append(var)
        for m in re.finditer(r"- name:\s*(.+)$", content, re.MULTILINE):
            info["steps"].append(m.group(1).strip())
    except FileNotFoundError:
        pass
    return info


def parse_env_vars_from_config():
    """Extract env var names from config.py."""
    env_vars = []
    config_path = os.path.join(ROOT_DIR, "scripts", "dify_sync", "config.py")
    try:
        with open(config_path, "r") as f:
            for m in re.finditer(r'os\.getenv\(["\']([^"\']+)', f.read()):
                var = m.group(1)
                if var not in env_vars:
                    env_vars.append(var)
    except FileNotFoundError:
        pass
    return env_vars


def collect_js_modules():
    """Collect JS module info: filename, line count."""
    modules = []
    js_dir = os.path.join(ROOT_DIR, "site", "js")
    if not os.path.isdir(js_dir):
        return modules
    for f in sorted(os.listdir(js_dir)):
        if f.endswith(".js"):
            path = os.path.join(js_dir, f)
            modules.append({"file": f, "lines": count_lines(path)})
    return modules


def collect_python_scripts():
    """Collect Python script info: filename, docstring, line count."""
    scripts = []
    for pattern in ["scripts/*.py", "scripts/dify_sync/*.py"]:
        for path in sorted(glob.glob(os.path.join(ROOT_DIR, pattern))):
            relpath = os.path.relpath(path, ROOT_DIR)
            docstring = ""
            try:
                with open(path, "r") as f:
                    content = f.read()
                m = re.search(r'"""(.+?)"""', content, re.DOTALL)
                if m:
                    docstring = m.group(1).strip().split("\n")[0]
            except Exception:
                pass
            scripts.append({
                "file": relpath,
                "lines": count_lines(path),
                "docstring": docstring,
            })
    return scripts


def collect_html_pages():
    """Collect HTML page info."""
    pages = []
    site_dir = os.path.join(ROOT_DIR, "site")
    if not os.path.isdir(site_dir):
        return pages
    for f in sorted(os.listdir(site_dir)):
        if f.endswith(".html"):
            pages.append(f)
    return pages


def main():
    meta = {
        "file_counts": {
            "summaries": count_files("data/summaries", "*.json"),
            "tweets": count_files("data/tweets", "*.json"),
            "sheets": count_files("data/sheets", "*.json"),
            "docs": count_files("data/docs", "*.md"),
            "html_pages": len(collect_html_pages()),
            "js_modules": count_files("site/js", "*.js"),
            "css_files": count_files("site/css", "*.css"),
            "workflows": count_files(".github/workflows", "*.yml"),
            "python_scripts": len(collect_python_scripts()),
        },
        "html_pages": collect_html_pages(),
        "js_modules": collect_js_modules(),
        "python_scripts": collect_python_scripts(),
        "css_lines": count_lines(os.path.join(ROOT_DIR, "site", "css", "style.css")),
        "dependencies": parse_requirements(
            os.path.join(ROOT_DIR, "scripts", "requirements.txt")
        ),
        "api_dependencies": parse_requirements(
            os.path.join(ROOT_DIR, "scripts", "dify_sync", "requirements-api.txt")
        ),
        "workflows": {},
        "env_vars": parse_env_vars_from_config(),
    }

    wf_dir = os.path.join(ROOT_DIR, ".github", "workflows")
    if os.path.isdir(wf_dir):
        for f in sorted(os.listdir(wf_dir)):
            if f.endswith(".yml"):
                meta["workflows"][f] = parse_workflow(os.path.join(wf_dir, f))

    json.dump(meta, sys.stdout, indent=2, ensure_ascii=False)
    print()


if __name__ == "__main__":
    main()
