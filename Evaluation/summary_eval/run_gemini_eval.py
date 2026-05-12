#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import os
import re
import time
from pathlib import Path

import google.generativeai as genai


SYSTEM_PROMPT = """Bạn là biên tập viên công nghệ AI tại một tòa soạn tin tức Việt Nam.
Tóm tắt chính xác, trung lập, dễ hiểu. Không bịa thông tin ngoài bài gốc.
Chỉ trả JSON đúng schema: {"summary": "..."}."""


def parse_summary_json(text: str) -> dict:
    text = (text or "").strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    cleaned = re.sub(r"^```json\s*|\s*```$", "", text, flags=re.IGNORECASE).strip()
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        pass

    match = re.search(r"\{.*\}", cleaned, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(0))
        except json.JSONDecodeError:
            pass

    # If the API response was cut mid-JSON, keep the generated summary text
    # instead of losing the whole batch.
    match = re.search(r'"summary"\s*:\s*"(.+)', cleaned, re.DOTALL)
    if match:
        value = match.group(1)
        value = value.rsplit('"', 1)[0] if '"' in value else value
        value = value.replace("\\n", " ").replace('\\"', '"')
        value = re.sub(r"\s+", " ", value).strip()
        if value:
            return {"summary": value}

    raise json.JSONDecodeError("Could not parse Gemini JSON response", text, 0)


def call_gemini(model, title: str, label: str, content: str) -> str:
    prompt = f"""Tóm tắt bài báo dưới đây.

Chỉ trả JSON:
{{"summary": "2-3 câu tiếng Việt, trung lập, bám sát bài gốc"}}

TIÊU ĐỀ: {title}
LOẠI BÀI: {label}

NỘI DUNG:
{content[:12000]}"""
    last_error = None
    for attempt in range(3):
        try:
            resp = model.generate_content(
                prompt,
                generation_config=genai.GenerationConfig(
                    temperature=0.2,
                    max_output_tokens=768,
                    response_mime_type="application/json",
                ),
            )
            data = parse_summary_json(resp.text)
            summary = str(data.get("summary", "")).strip()
            if summary:
                return summary
            last_error = ValueError("Gemini returned JSON without a summary")
        except Exception as exc:
            last_error = exc
            time.sleep(2 + attempt)
    raise RuntimeError(f"Gemini summary failed after retries: {last_error}")


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--input", default="eval_articles.csv")
    p.add_argument("--output", default="eval_articles_with_gemini.csv")
    p.add_argument("--model", default=os.getenv("GEMINI_MODEL", "gemini-2.5-flash"))
    p.add_argument("--delay", type=float, default=7.0)
    p.add_argument("--limit", type=int, default=0)
    args = p.parse_args()

    api_key =
    if not api_key:
        raise SystemExit("Set GEMINI_API_KEY before running.")

    genai.configure(api_key=api_key)
    model = genai.GenerativeModel(args.model, system_instruction=SYSTEM_PROMPT)

    with Path(args.input).open(newline="", encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f))
    fieldnames = list(rows[0]) if rows else []

    def save() -> None:
        with Path(args.output).open("w", newline="", encoding="utf-8-sig") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)

    done = 0
    for i, r in enumerate(rows, 1):
        if args.limit and done >= args.limit:
            break
        if r.get("gemini_summary", "").strip():
            continue
        print(f"[{i}/{len(rows)}] {r.get('title', '')[:80]}")
        r["gemini_summary"] = call_gemini(model, r["title"], r["label"], r["content"])
        done += 1
        save()
        if i < len(rows):
            time.sleep(args.delay)

    print(f"Wrote {args.output}")


if __name__ == "__main__":
    main()
