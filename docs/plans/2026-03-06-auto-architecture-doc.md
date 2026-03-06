# Auto-Update Architecture Document — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Automatically regenerate `docs/architecture-overview.md` via GitHub Action when code changes, while preserving manually-written sections.

**Architecture:** A Python script collects codebase metadata (file counts, dependencies, workflows, env vars, code stats), then sends it along with the current doc to GPT-4o to regenerate the full document. Sections wrapped in `<!-- manual-start -->` / `<!-- manual-end -->` tags are preserved verbatim. A GitHub Action triggers this on push to `main`.

**Tech Stack:** Python 3.12, OpenAI GPT-4o, GitHub Actions

---

### Task 1: Add Manual Override Tags to Architecture Doc

**Files:**
- Modify: `docs/architecture-overview.md`

**Step 1: Add `<!-- manual-start -->` / `<!-- manual-end -->` tags**

Wrap sections that should NOT be auto-regenerated. These are opinion/strategy sections that require human judgment:

```markdown
<!-- manual-start:risks -->
## 10. 風險與限制
... (existing content stays unchanged) ...
<!-- manual-end:risks -->

<!-- manual-start:readiness -->
## 11. 正式環境準備度評估
... (existing content stays unchanged) ...
<!-- manual-end:readiness -->

<!-- manual-start:improvements -->
## 12. 改善建議
... (existing content stays unchanged) ...
<!-- manual-end:improvements -->
```

All other sections (1-9, appendix) will be auto-generated from codebase analysis.

**Step 2: Verify tags are correctly placed**

Run: `grep -n "manual-start\|manual-end" docs/architecture-overview.md`
Expected: 6 lines (3 start + 3 end tags)

**Step 3: Commit**

```bash
git add docs/architecture-overview.md
git commit -m "chore: add manual override tags to architecture doc"
```

---

### Task 2: Create Codebase Metadata Collector Script

**Files:**
- Create: `scripts/collect_codebase_meta.py`

**Step 1: Write the metadata collector**

This script scans the repo and produces a JSON summary of the codebase state.

```python
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
        # Name
        m = re.search(r"^name:\s*(.+)$", content, re.MULTILINE)
        if m:
            info["name"] = m.group(1).strip()
        # Triggers
        for trigger in ["schedule", "workflow_dispatch", "workflow_run", "push"]:
            if trigger in content:
                info["triggers"].append(trigger)
        # Env vars (from secrets)
        for m in re.finditer(r"secrets\.([A-Z_]+)", content):
            var = m.group(1)
            if var not in info["env_vars"]:
                info["env_vars"].append(var)
        # Step names
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

    # Parse all workflows
    wf_dir = os.path.join(ROOT_DIR, ".github", "workflows")
    if os.path.isdir(wf_dir):
        for f in sorted(os.listdir(wf_dir)):
            if f.endswith(".yml"):
                meta["workflows"][f] = parse_workflow(os.path.join(wf_dir, f))

    json.dump(meta, sys.stdout, indent=2, ensure_ascii=False)
    print()


if __name__ == "__main__":
    main()
```

**Step 2: Test the collector**

Run: `python3 scripts/collect_codebase_meta.py | python3 -m json.tool | head -40`
Expected: Valid JSON with file counts, modules, scripts, etc.

**Step 3: Commit**

```bash
git add scripts/collect_codebase_meta.py
git commit -m "feat: add codebase metadata collector for architecture doc"
```

---

### Task 3: Create Architecture Doc Generator Script

**Files:**
- Create: `scripts/generate_architecture_doc.py`

**Step 1: Write the generator**

This script:
1. Runs the metadata collector
2. Reads the current architecture doc
3. Extracts `<!-- manual-start:X -->` sections
4. Sends metadata + manual sections to GPT-4o
5. Writes the updated doc

```python
#!/usr/bin/env python3
"""Regenerate docs/architecture-overview.md using codebase metadata + GPT-4o."""

import json
import os
import re
import subprocess
import sys
from datetime import date

from openai import OpenAI

ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
ARCH_DOC = os.path.join(ROOT_DIR, "docs", "architecture-overview.md")


def collect_metadata():
    """Run collect_codebase_meta.py and return parsed JSON."""
    result = subprocess.run(
        [sys.executable, os.path.join(ROOT_DIR, "scripts", "collect_codebase_meta.py")],
        capture_output=True, text=True
    )
    if result.returncode != 0:
        print(f"Metadata collection failed: {result.stderr}", file=sys.stderr)
        sys.exit(1)
    return json.loads(result.stdout)


def extract_manual_sections(doc_content):
    """Extract sections between <!-- manual-start:X --> and <!-- manual-end:X --> tags."""
    sections = {}
    pattern = r"<!-- manual-start:(\w+) -->\n(.*?)<!-- manual-end:\1 -->"
    for match in re.finditer(pattern, doc_content, re.DOTALL):
        sections[match.group(1)] = match.group(2).strip()
    return sections


def generate_doc(metadata, manual_sections):
    """Call GPT-4o to regenerate the architecture document."""
    client = OpenAI()

    manual_block = ""
    for key, content in manual_sections.items():
        manual_block += f"\n### Manual Section: {key}\n{content}\n"

    prompt = f"""You are a technical documentation writer. Regenerate the full architecture document for the 投資Talk君 project.

<codebase_metadata>
{json.dumps(metadata, indent=2, ensure_ascii=False)}
</codebase_metadata>

<manual_sections_to_preserve>
{manual_block}
</manual_sections_to_preserve>

<instructions>
1. Write the COMPLETE architecture document in Traditional Chinese (繁體中文)
2. Follow the EXACT same 12-section structure as before:
   - 1. 專案概述
   - 2. 系統架構圖 (ASCII art diagram)
   - 3. 資料來源與擷取
   - 4. 資料處理管線
   - 5. RAG 知識庫架構
   - 6. 前端架構
   - 7. 部署架構
   - 8. 自動化流程（GitHub Actions）
   - 9. 成本估算
   - 10. 風險與限制
   - 11. 正式環境準備度評估
   - 12. 改善建議
   - 附錄：關鍵檔案索引

3. For sections 10, 11, 12: wrap them in <!-- manual-start:X --> / <!-- manual-end:X --> tags and use the EXACT content from <manual_sections_to_preserve>. Do NOT modify these sections.

4. For all other sections: regenerate using the codebase metadata. Use ACCURATE numbers from the metadata (file counts, line counts, module names, etc.)

5. Start with this header:
   # 投資Talk君 — 技術架構文件
   > **文件用途**：供開發團隊討論、改善與未來規劃使用
   > **最後更新**：{date.today().isoformat()}
   > **專案倉庫**：https://github.com/cyt9999/talk-library
   > **此文件由 CI 自動產生**，手動維護段落以 `<!-- manual -->` 標記保護。

6. Use tables, code blocks, and ASCII diagrams where appropriate
7. Be precise — use exact file paths, exact counts, exact dependency versions from metadata
8. The document should be comprehensive (500+ lines) and production-quality
</instructions>

Output ONLY the markdown document, no wrapping code fences.
"""

    response = client.chat.completions.create(
        model="gpt-4o",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.2,
        max_tokens=8000,
    )

    return response.choices[0].message.content


def main():
    dry_run = "--dry-run" in sys.argv

    print("Collecting codebase metadata...", file=sys.stderr)
    metadata = collect_metadata()

    manual_sections = {}
    if os.path.exists(ARCH_DOC):
        print("Extracting manual sections from existing doc...", file=sys.stderr)
        with open(ARCH_DOC, "r") as f:
            manual_sections = extract_manual_sections(f.read())
        print(f"  Found {len(manual_sections)} manual sections: {list(manual_sections.keys())}", file=sys.stderr)
    else:
        print("No existing doc found, generating from scratch.", file=sys.stderr)

    print("Generating architecture document with GPT-4o...", file=sys.stderr)
    doc = generate_doc(metadata, manual_sections)

    if dry_run:
        print(doc)
    else:
        with open(ARCH_DOC, "w") as f:
            f.write(doc)
            if not doc.endswith("\n"):
                f.write("\n")
        print(f"Written to {ARCH_DOC}", file=sys.stderr)


if __name__ == "__main__":
    main()
```

**Step 2: Test with dry-run**

Run: `python3 scripts/generate_architecture_doc.py --dry-run 2>&1 | tail -20`
Expected: Markdown output with updated stats, manual sections preserved with tags

**Step 3: Run for real and verify manual sections preserved**

Run: `python3 scripts/generate_architecture_doc.py`
Then: `grep -c "manual-start\|manual-end" docs/architecture-overview.md`
Expected: 6 (3 pairs of tags preserved)

**Step 4: Commit**

```bash
git add scripts/generate_architecture_doc.py
git commit -m "feat: add architecture doc generator with manual section preservation"
```

---

### Task 4: Create GitHub Actions Workflow

**Files:**
- Create: `.github/workflows/update-architecture-doc.yml`

**Step 1: Write the workflow**

```yaml
name: Update Architecture Doc

on:
  push:
    branches: [main]
    paths:
      - 'scripts/**'
      - 'site/**'
      - '.github/workflows/**'
      - 'data/docs/**'
      - 'render.yaml'
      - 'scripts/requirements.txt'
  workflow_dispatch:

jobs:
  update-doc:
    runs-on: ubuntu-latest
    env:
      OPENAI_API_KEY: ${{ secrets.OPENAI_API_KEY }}
    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-python@v5
        with:
          python-version: '3.12'

      - name: Install dependencies
        run: pip install openai

      - name: Generate architecture doc
        run: python3 scripts/generate_architecture_doc.py

      - name: Check for changes
        id: diff
        run: |
          git diff --quiet docs/architecture-overview.md || echo "changed=true" >> "$GITHUB_OUTPUT"

      - name: Commit and push
        if: steps.diff.outputs.changed == 'true'
        run: |
          git config user.name "github-actions[bot]"
          git config user.email "github-actions[bot]@users.noreply.github.com"
          git add docs/architecture-overview.md
          git commit -m "docs: auto-update architecture overview"
          git push
```

**Step 2: Verify YAML syntax**

Run: `python3 -c "import yaml; yaml.safe_load(open('.github/workflows/update-architecture-doc.yml'))"`
Note: If `pyyaml` not installed, just visually verify the YAML is correct.

**Step 3: Commit**

```bash
git add .github/workflows/update-architecture-doc.yml
git commit -m "ci: add workflow to auto-update architecture doc on code changes"
```

---

### Task 5: End-to-End Test

**Step 1: Push all changes and verify workflow triggers**

```bash
git push
```

**Step 2: Check GitHub Actions**

Go to: `https://github.com/cyt9999/talk-library/actions/workflows/update-architecture-doc.yml`
Expected: Workflow runs, generates doc, commits if changed.

**Step 3: Pull and verify the auto-generated doc**

```bash
git pull
```

Then verify:
- `docs/architecture-overview.md` has updated date
- Manual sections (10, 11, 12) are preserved with tags
- File counts and line numbers match current codebase
- No broken formatting

---

## Cost Impact

Each architecture doc regeneration uses ~4K input tokens + ~8K output tokens of GPT-4o:
- **Per run**: ~$0.06
- **Estimated monthly** (assuming 30 pushes/month): ~$1.80
- Only triggers on code/config changes, not data changes (summaries, tweets, etc.)
