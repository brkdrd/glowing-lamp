"""
Task 2: Order Risk Classification Pipeline.

Reads sales transactions from a CSV file, sends each transaction to an LLM
(via OpenRouter API) for risk classification, and saves structured results
as JSON.

Categories:
    - normal: ordinary retail transaction
    - bulk_order: legitimate wholesale order (large quantity)
    - data_error: likely input mistake (e.g. huge sales with quantity=1)
    - loss_making: deeply unprofitable due to high discount
    - return: a return transaction (negative quantity)
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import re
import sys
import time
from pathlib import Path

import requests
from dotenv import load_dotenv

load_dotenv()

OPENROUTER_API_URL = "https://openrouter.ai/api/v1/chat/completions"
DEFAULT_MODEL = "qwen/qwen-2.5-72b-instruct"
MAX_RETRIES = 3
RETRY_DELAY_SECONDS = 5

SYSTEM_PROMPT = """You are a data analyst classifying retail transactions for a sales audit.

For each transaction, decide which ONE of the following categories it belongs to:
- "normal": ordinary single-item or small retail transaction with positive profit
- "bulk_order": legitimate wholesale order (large quantity, e.g. 20+ units)
- "data_error": suspicious record likely caused by data entry mistake (e.g. very high sales with quantity=1)
- "loss_making": transaction with deeply negative profit due to high discount
- "return": a return / refund transaction (negative quantity)

Respond with a single JSON object and nothing else. The JSON MUST have this exact shape:

{
  "category": "<one of: normal, bulk_order, data_error, loss_making, return>",
  "confidence": <float between 0 and 1>,
  "reason": "<one short sentence explaining the decision in English>"
}

Do NOT include markdown, code fences, prose, or any text outside the JSON object."""


def build_user_message(row: dict) -> str:
    """Format a single transaction row for the LLM."""
    return (
        f"Order ID: {row['Order ID']}\n"
        f"Category / Sub-Category: {row['Category']} / {row['Sub-Category']}\n"
        f"Quantity: {row['Quantity']}\n"
        f"Unit Price: {row['Unit Price']}\n"
        f"Discount: {row['Discount']}\n"
        f"Sales: {row['Sales']}\n"
        f"Profit: {row['Profit']}\n"
    )


def extract_json(text: str) -> dict:
    """Extract the first JSON object from the model output, tolerating code fences."""
    cleaned = text.strip()
    cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
    cleaned = re.sub(r"\s*```$", "", cleaned)
    match = re.search(r"\{.*\}", cleaned, re.DOTALL)
    if not match:
        raise ValueError(f"No JSON object found in model output: {text!r}")
    return json.loads(match.group(0))


def classify_row(row: dict, api_key: str, model: str) -> dict:
    """Send one row to the LLM and parse the response."""
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": build_user_message(row)},
        ],
        "temperature": 0.0,
        "max_tokens": 200,
    }
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    last_error: Exception | None = None
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            response = requests.post(
                OPENROUTER_API_URL, headers=headers, json=payload, timeout=60
            )
            response.raise_for_status()
            data = response.json()
            content = data["choices"][0]["message"]["content"]
            return extract_json(content)
        except (requests.RequestException, ValueError, KeyError) as exc:
            last_error = exc
            if attempt < MAX_RETRIES:
                time.sleep(RETRY_DELAY_SECONDS)
            else:
                break

    return {
        "category": "error",
        "confidence": 0.0,
        "reason": f"Classification failed after {MAX_RETRIES} attempts: {last_error}",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Classify sales transactions via LLM.")
    parser.add_argument("--input", default="data/superstore_sales.csv", help="Path to input CSV.")
    parser.add_argument("--output", default="data/classified_orders.json", help="Path to output JSON.")
    parser.add_argument("--limit", type=int, default=50, help="How many rows to classify.")
    parser.add_argument("--model", default=DEFAULT_MODEL, help="OpenRouter model slug.")
    args = parser.parse_args()

    api_key = os.getenv("OPENROUTER_API_KEY")
    if not api_key:
        print("ERROR: OPENROUTER_API_KEY is not set. Create a .env file (see .env.example).", file=sys.stderr)
        return 1

    input_path = Path(args.input)
    output_path = Path(args.output)
    if not input_path.exists():
        print(f"ERROR: input file not found: {input_path}", file=sys.stderr)
        return 1

    output_path.parent.mkdir(parents=True, exist_ok=True)

    with input_path.open(encoding="utf-8") as f:
        reader = csv.DictReader(f)
        rows = list(reader)

    rows_to_process = rows[: args.limit]
    print(f"Classifying {len(rows_to_process)} rows using model {args.model}...")

    results = []
    for i, row in enumerate(rows_to_process, start=1):
        classification = classify_row(row, api_key=api_key, model=args.model)
        results.append({
            "order_id": row["Order ID"],
            "order_date": row["Order Date"],
            "category": row["Category"],
            "sub_category": row["Sub-Category"],
            "quantity": int(row["Quantity"]),
            "sales": float(row["Sales"]),
            "profit": float(row["Profit"]),
            "discount": float(row["Discount"]),
            "llm_classification": classification,
        })
        print(f"  [{i}/{len(rows_to_process)}] {row['Order ID']} -> {classification.get('category')}")

    with output_path.open("w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)

    print(f"\nDone. Saved {len(results)} classifications to {output_path}")

    summary: dict[str, int] = {}
    for r in results:
        cat = r["llm_classification"].get("category", "unknown")
        summary[cat] = summary.get(cat, 0) + 1
    print("\nCategory distribution:")
    for cat, count in sorted(summary.items(), key=lambda x: -x[1]):
        print(f"  {cat}: {count}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
