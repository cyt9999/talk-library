#!/usr/bin/env python3
"""Interactive Q&A CLI using OpenAI Responses API with file search."""

import sys

from openai import OpenAI

from config import VECTOR_STORE_ID

client = OpenAI()

SYSTEM_PROMPT = """\
你是「投資Talk君 AI」，專門根據Talk君的YouTube影片摘要和X平台短評回答投資相關問題。

## 規則

1. **僅根據提供的資料回答**：如果資料中沒有相關內容，請誠實說明「目前資料中沒有這方面的分析」。絕對不要編造或猜測。
2. **附上參考來源**：每個回答必須附上參考來源，包括影片標題、日期或X貼文日期。
3. **使用繁體中文**：所有回答必須使用繁體中文。
4. **不提供投資建議**：絕對不要使用「建議買入」「應該賣出」等投資建議用語。你只是整理和呈現Talk君的分析內容。
5. **保持客觀**：如實呈現Talk君的觀點，不加入個人判斷。
"""


def ask(question):
    """Send a question to the Responses API with file search."""
    response = client.responses.create(
        model="gpt-4o",
        tools=[{
            "type": "file_search",
            "vector_store_ids": [VECTOR_STORE_ID]
        }],
        input=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": question}
        ]
    )

    # Extract text and citations from response
    answer_parts = []
    citations = []
    for item in response.output:
        if item.type == "message":
            for block in item.content:
                if block.type == "output_text":
                    answer_parts.append(block.text)
                    for ann in getattr(block, "annotations", []):
                        if ann.type == "file_citation":
                            citations.append(ann)

    return "\n".join(answer_parts), citations


def main():
    if not VECTOR_STORE_ID:
        print("Error: VECTOR_STORE_ID not set in .env")
        print("Run convert_and_upload.py first to create a vector store.")
        sys.exit(1)

    print("投資Talk君 AI — 互動問答")
    print("輸入問題，或輸入 quit 離開\n")

    while True:
        try:
            question = input("問題：").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n再見！")
            break

        if not question:
            continue
        if question.lower() in ("quit", "exit", "q"):
            print("再見！")
            break

        print("\n思考中...\n")
        try:
            answer, citations = ask(question)
            print(answer)
            if citations:
                print("\n---")
                print("參考來源：")
                seen = set()
                for c in citations:
                    filename = getattr(c, "filename", None) or "unknown"
                    if filename not in seen:
                        seen.add(filename)
                        print(f"  - {filename}")
            print()
        except Exception as e:
            print(f"Error: {e}\n", file=sys.stderr)


if __name__ == "__main__":
    main()
