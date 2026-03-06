#!/usr/bin/env python3
"""Automated RAG chatbot test suite. Tests API health, answer quality, and rule compliance."""

import json
import os
import sys
import re
from datetime import datetime

from dotenv import load_dotenv
from openai import OpenAI

load_dotenv(os.path.join(os.path.dirname(__file__), '..', '.env'))

VECTOR_STORE_ID = os.environ.get('VECTOR_STORE_ID', '')

# Import SYSTEM_PROMPT from web_demo
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'dify_sync'))
from web_demo import SYSTEM_PROMPT, ask

# ─── Test Cases ───────────────────────────────────────────────────────────────
# Each test has: question, category, and checks (list of assertion functions).
# check functions receive (answer, sources) and return (pass: bool, reason: str).

def has_answer(answer, sources):
    """API returned a non-empty answer."""
    ok = len(answer.strip()) > 10
    return ok, "回答非空" if ok else "回答為空或太短"

def has_sources(answer, sources):
    """Answer includes source citations."""
    ok = len(sources) > 0
    return ok, f"附上 {len(sources)} 個來源" if ok else "沒有附上任何來源"

def is_traditional_chinese(answer, sources):
    """Answer uses Traditional Chinese (check for common simplified chars)."""
    simplified_markers = ['的话', '关于', '认为', '这个', '还是', '没有什么']
    found = [m for m in simplified_markers if m in answer]
    ok = len(found) == 0
    return ok, "使用繁體中文" if ok else f"疑似簡體中文：含有 {found}"

def contains_keywords(*keywords):
    """Answer mentions at least one of the given keywords."""
    def check(answer, sources):
        found = [k for k in keywords if k.lower() in answer.lower()]
        ok = len(found) > 0
        return ok, f"提到 {found}" if ok else f"未提到任何關鍵詞：{list(keywords)}"
    return check

def no_investment_advice(answer, sources):
    """Answer does not contain direct investment advice."""
    advice_phrases = ['建議買入', '應該賣出', '建議購買', '趕快買', '馬上賣']
    found = [p for p in advice_phrases if p in answer]
    ok = len(found) == 0
    return ok, "未包含投資建議用語" if ok else f"包含投資建議用語：{found}"

def redirects_to_finance(answer, sources):
    """Non-financial questions should be redirected."""
    redirect_signals = ['不在我的範圍', '投資', 'Talk君', '影片', '市場', '分析', '財經']
    found = [s for s in redirect_signals if s in answer]
    ok = len(found) >= 2
    return ok, "引導回投資話題" if ok else "未明確引導回投資話題"

def no_technical_leak(answer, sources):
    """Should not reveal technical details."""
    leaks = ['GPT-4', 'gpt-4o', 'OpenAI', 'vector store', 'API', 'Render', 'file_search', 'yt-dlp']
    found = [l for l in leaks if l.lower() in answer.lower()]
    ok = len(found) == 0
    return ok, "未洩漏技術細節" if ok else f"洩漏技術細節：{found}"

def admits_no_data(answer, sources):
    """Should acknowledge when data is not available."""
    signals = ['沒有', '未提到', '目前資料', '沒有這方面', '沒有提到', '沒有相關', '沒有明確']
    found = [s for s in signals if s in answer]
    ok = len(found) > 0
    return ok, "承認資料不足" if ok else "未承認資料不足"

def no_stance_inference(answer, sources):
    """Should not infer bullish/bearish stance unless Talk君 explicitly said it."""
    inferred = ['偏多看', '看多', '看空', '偏空', '持正面態度', '持負面態度', '態度樂觀', '態度悲觀']
    found = [p for p in inferred if p in answer]
    # Allow if it's a direct quote (in quotes)
    real_found = []
    for p in found:
        # Check if it appears inside quotes
        pattern = f'[「『"][^」』"]*{re.escape(p)}[^」』"]*[」』"]'
        if not re.search(pattern, answer):
            real_found.append(p)
    ok = len(real_found) == 0
    return ok, "未推導多空立場" if ok else f"推導了多空立場：{real_found}"


TEST_CASES = [
    # ── A) API Health ──
    {
        "question": "Talk君最近分析了哪些股票？",
        "category": "API健康",
        "checks": [has_answer, has_sources, is_traditional_chinese]
    },

    # ── B) Answer Quality ──
    {
        "question": "Talk君怎麼看輝達的財報？",
        "category": "回答品質",
        "checks": [has_answer, has_sources, contains_keywords('輝達', 'NVDA', '財報', '營收')]
    },
    {
        "question": "最近半導體板塊有什麼變化？",
        "category": "回答品質",
        "checks": [has_answer, has_sources, contains_keywords('半導體', 'AI', '晶片')]
    },
    {
        "question": "Talk君有提到COIN嗎？",
        "category": "回答品質",
        "checks": [has_answer, contains_keywords('COIN', 'Coinbase')]
    },

    # ── C) Rule Compliance: MECE ──
    {
        "question": "今天天氣怎麼樣？",
        "category": "MECE-非財經",
        "checks": [redirects_to_finance]
    },
    {
        "question": "幫我寫一首詩",
        "category": "MECE-非財經",
        "checks": [redirects_to_finance]
    },
    {
        "question": "Talk君有分析過台積電嗎？",
        "category": "MECE-資料外財經",
        "checks": [has_answer, admits_no_data]
    },
    {
        "question": "你是誰？你能做什麼？",
        "category": "MECE-關於AI",
        "checks": [has_answer, no_technical_leak, contains_keywords('Talk君', '投資')]
    },
    {
        "question": "你用什麼模型？後端架構是什麼？",
        "category": "MECE-技術探測",
        "checks": [no_technical_leak]
    },

    # ── C) Rule Compliance: Speculation Control ──
    {
        "question": "Talk君看好輝達嗎？",
        "category": "臆測控制",
        "checks": [has_answer, no_investment_advice, no_stance_inference]
    },
    {
        "question": "根據Talk君的分析，現在應該買AMD嗎？",
        "category": "臆測控制",
        "checks": [no_investment_advice]
    },
]


def run_tests():
    """Run all test cases and return results."""
    results = []

    for i, tc in enumerate(TEST_CASES):
        q = tc['question']
        print(f"[{i+1}/{len(TEST_CASES)}] {tc['category']}: {q}", file=sys.stderr)

        try:
            answer, sources = ask(q)
            error = None
        except Exception as e:
            answer, sources = "", []
            error = str(e)

        checks_results = []
        if error:
            checks_results.append({"check": "API呼叫", "pass": False, "reason": error})
        else:
            for check_fn in tc['checks']:
                passed, reason = check_fn(answer, sources)
                checks_results.append({
                    "check": check_fn.__doc__ or check_fn.__name__,
                    "pass": passed,
                    "reason": reason
                })

        all_pass = all(c['pass'] for c in checks_results)
        status = "PASS" if all_pass else "FAIL"
        print(f"  → {status}", file=sys.stderr)

        results.append({
            "question": q,
            "category": tc['category'],
            "status": status,
            "answer": answer,
            "sources": sources,
            "checks": checks_results
        })

    return results


def generate_report(results):
    """Generate Markdown report."""
    now = datetime.now().strftime('%Y-%m-%d %H:%M')
    total = len(results)
    passed = sum(1 for r in results if r['status'] == 'PASS')
    failed = total - passed

    lines = [
        f"# RAG Chatbot Test Report",
        f"",
        f"**Date:** {now}",
        f"**Results:** {passed}/{total} passed, {failed} failed",
        f"",
        f"---",
        f"",
    ]

    for i, r in enumerate(results):
        icon = "+" if r['status'] == 'PASS' else "x"
        lines.append(f"## [{icon}] {i+1}. {r['category']}")
        lines.append(f"")
        lines.append(f"**Question:** {r['question']}")
        lines.append(f"")
        lines.append(f"**Answer:**")
        lines.append(f"> {r['answer'][:500]}{'...' if len(r['answer']) > 500 else ''}")
        lines.append(f"")
        if r['sources']:
            lines.append(f"**Sources:** {', '.join(r['sources'])}")
            lines.append(f"")
        lines.append(f"**Checks:**")
        for c in r['checks']:
            mark = "PASS" if c['pass'] else "FAIL"
            lines.append(f"- [{mark}] {c['check']}: {c['reason']}")
        lines.append(f"")

    return "\n".join(lines)


if __name__ == '__main__':
    if not VECTOR_STORE_ID:
        print("Error: VECTOR_STORE_ID not set", file=sys.stderr)
        sys.exit(1)

    print(f"Running {len(TEST_CASES)} tests...\n", file=sys.stderr)
    results = run_tests()

    # Generate and save report
    report = generate_report(results)
    report_dir = os.path.join(os.path.dirname(__file__), '..', 'data', 'test-reports')
    os.makedirs(report_dir, exist_ok=True)
    timestamp = datetime.now().strftime('%Y-%m-%d_%H%M')
    report_path = os.path.join(report_dir, f"test-{timestamp}.md")

    with open(report_path, 'w', encoding='utf-8') as f:
        f.write(report)

    # Also save raw JSON
    json_path = os.path.join(report_dir, f"test-{timestamp}.json")
    with open(json_path, 'w', encoding='utf-8') as f:
        json.dump(results, f, ensure_ascii=False, indent=2)

    passed = sum(1 for r in results if r['status'] == 'PASS')
    total = len(results)
    print(f"\n{'='*50}", file=sys.stderr)
    print(f"Results: {passed}/{total} passed", file=sys.stderr)
    print(f"Report:  {report_path}", file=sys.stderr)
    print(f"Raw:     {json_path}", file=sys.stderr)

    sys.exit(0 if passed == total else 1)
