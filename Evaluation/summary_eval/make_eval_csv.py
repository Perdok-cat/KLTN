#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import html
import random
import re
from collections import defaultdict
from pathlib import Path


def clean_text(value: str) -> str:
    value = html.unescape(value or "")
    value = re.sub(r"<[^>]+>", " ", value)
    return re.sub(r"\s+", " ", value).strip()


def split_sentences(text: str) -> list[str]:
    text = clean_text(text)
    parts = re.split(r"(?<=[.!?。！？])\s+", text)
    return [p.strip() for p in parts if p.strip()]


def lead3(text: str) -> str:
    return " ".join(split_sentences(text)[:3])


def read_rows(path: Path) -> list[dict]:
    with path.open(newline="", encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def write_rows(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--source", default="Data/FINAL_DATA.csv")
    p.add_argument("--out", default="eval_articles.csv")
    p.add_argument("--per-label", type=int, default=20)
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--min-chars", type=int, default=500)
    p.add_argument("--reference", choices=["blank", "source_summary", "lead3"], default="blank")
    args = p.parse_args()

    rows = read_rows(Path(args.source))
    groups: dict[str, list[dict]] = defaultdict(list)
    for r in rows:
        label = clean_text(r.get("label", "")).upper()
        content = clean_text(r.get("content", ""))
        if label and label != "NOISE" and len(content) >= args.min_chars:
            groups[label].append(r)

    rng = random.Random(args.seed)
    selected: list[dict] = []
    for label in sorted(groups):
        pool = groups[label]
        rng.shuffle(pool)
        selected.extend(pool[: args.per_label])

    out_rows = []
    for i, r in enumerate(selected, 1):
        content = clean_text(r.get("content", ""))
        ref = ""
        if args.reference == "source_summary":
            ref = clean_text(r.get("summary", ""))
        elif args.reference == "lead3":
            ref = lead3(content)

        out_rows.append(
            {
                "eval_id": f"E{i:04d}",
                "title": clean_text(r.get("title", "")),
                "label": clean_text(r.get("label", "")),
                "link": clean_text(r.get("link", "")),
                "source": clean_text(r.get("source", "")),
                "published": clean_text(r.get("published", r.get("pub_date", ""))),
                "content": content,
                "content_len": len(content),
                "reference_summary": ref,
                "lead3_summary": lead3(content),
                "gemini_summary": "",
                "notes": "",
            }
        )

    if not out_rows:
        raise SystemExit("No rows selected. Check source path or filters.")

    write_rows(Path(args.out), out_rows)
    print(f"Wrote {len(out_rows)} rows -> {args.out}")


if __name__ == "__main__":
    main()
