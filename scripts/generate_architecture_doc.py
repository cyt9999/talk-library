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
