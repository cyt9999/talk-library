import os
from openai import OpenAI
from config import VECTOR_STORE_ID

client = OpenAI()

def test_ask():
    print("Asking question...")
    response = client.responses.create(
        model="gpt-4o",
        tools=[{
            "type": "file_search",
            "vector_store_ids": [VECTOR_STORE_ID]
        }],
        input=[
            {"role": "user", "content": "NVDA 最近的分析是什麼？請附上來源。"}
        ]
    )

    print("\n--- Raw Response Output ---")
    for item in response.output:
        if item.type == "message":
            for block in item.content:
                if block.type == "output_text":
                    print(f"Text block: {block.text[:100]}...")
                    if hasattr(block, "annotations"):
                        for ann in block.annotations:
                            print(f"\nAnnotation type: {ann.type}")
                            if ann.type == "file_citation":
                                print(f"File ID: {getattr(ann.file_citation, 'file_id', 'N/A')}")
                                print(f"Quote: {getattr(ann.file_citation, 'quote', 'N/A')}")
                                print(f"Text: {ann.text}")
                                # Try to get filename
                                try:
                                    file_info = client.files.retrieve(ann.file_citation.file_id)
                                    print(f"Filename: {file_info.filename}")
                                except Exception as e:
                                    print(f"Error getting file info: {e}")

if __name__ == "__main__":
    test_ask()
