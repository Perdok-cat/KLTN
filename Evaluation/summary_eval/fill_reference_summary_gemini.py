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


SYSTEM_PROMPT = """Bạn là biên tập viên tin tức tiếng Việt.
Viết reference_summary để đánh giá hệ thống tóm tắt.
Chỉ dùng thông tin có trong bài. Không thêm kiến thức ngoài nguồn.
Viết 3-4 câu, 80-120 từ, trung lập, tự nhiên, như người biên tập.
Giữ tên riêng, số liệu, mốc thời gian quan trọng nếu có.
Bỏ quảng cáo, phần rác, câu lặp, câu dẫn nhập sáo rỗng.
Không bullet, không tiêu đề, không trích nguyên văn dài.
Chỉ trả JSON đúng schema."""


def parse_json(text: str) -> dict:
    text = (text or "").strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if match:
            try:
                return json.loads(match.group(0))
            except json.JSONDecodeError:
                pass

        match = re.search(r'"reference_summary"\s*:\s*"(.+)', text, re.DOTALL)
        if match:
            value = match.group(1)
            value = value.rsplit('"', 1)[0] if '"' in value else value
            value = value.replace("\\n", " ").replace('\\"', '"')
            value = re.sub(r"\s+", " ", value).strip()
            if value:
                return {"reference_summary": value}

        cleaned = re.sub(r"^```json\s*|\s*```$", "", text, flags=re.IGNORECASE).strip()
        cleaned = re.sub(r"\s+", " ", cleaned)
        if cleaned:
            return {"reference_summary": cleaned}
        raise


def make_reference(model, title: str, label: str, content: str) -> str:
    prompt = f"""Hãy viết reference_summary cho bài báo sau.

Chỉ trả JSON:
{{"reference_summary": "3-4 câu tiếng Việt, 80-120 từ"}}

TIÊU ĐỀ: {title}

NỘI DUNG:
{content[:20000]}"""

    last_error = None
    for attempt in range(3):
        try:
            resp = model.generate_content(
                prompt,
                generation_config=genai.GenerationConfig(
                    temperature=0.1,
                    max_output_tokens=1536,
                    response_mime_type="application/json",
                ),
            )
            data = parse_json(resp.text)
            summary = str(data["reference_summary"]).strip()
            if summary:
                return summary
        except Exception as exc:
            last_error = exc
            time.sleep(2 + attempt)
    raise RuntimeError(f"Gemini reference failed after retries: {last_error}")


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--input", default="eval_articles.csv")
    p.add_argument("--output", default="eval_articles_gemini_ref.csv")
    p.add_argument("--model", default=os.getenv("GEMINI_REFERENCE_MODEL", "gemini-3.1-pro-preview"))
    p.add_argument("--delay", type=float, default=8.0)
    p.add_argument("--limit", type=int, default=0)
    p.add_argument("--overwrite", dest="overwrite", action="store_true")
    p.add_argument("--no-overwrite", dest="overwrite", action="store_false")
    p.set_defaults(overwrite=True)
    args = p.parse_args()

    api_key = 
    if not api_key:
        raise SystemExit("Set GEMINI_API_KEY before running.")

    genai.configure(api_key=api_key)
    model = genai.GenerativeModel(args.model, system_instruction=SYSTEM_PROMPT)

    in_path = Path(args.input)
    out_path = Path(args.output)
    with in_path.open(newline="", encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f))

    def save() -> None:
        with out_path.open("w", newline="", encoding="utf-8-sig") as f:
            writer = csv.DictWriter(f, fieldnames=list(rows[0]))
            writer.writeheader()
            writer.writerows(rows)

    done = 0
    for i, row in enumerate(rows, 1):
        if args.limit and done >= args.limit:
            break
        if row.get("reference_summary", "").strip() and not args.overwrite:
            continue

        print(f"[{i}/{len(rows)}] {row.get('title', '')[:90]}")
        row["reference_summary"] = make_reference(
            model,
            row.get("title", ""),
            row.get("label", ""),
            row.get("content", ""),
        )
        done += 1
        save()
        if i < len(rows):
            time.sleep(args.delay)

    print(f"Filled {done} rows -> {out_path}")


if __name__ == "__main__":
    main()
