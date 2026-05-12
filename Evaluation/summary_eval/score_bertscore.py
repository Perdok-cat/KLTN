#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
from collections import defaultdict
from pathlib import Path


def read_rows(path: Path) -> list[dict]:
    with path.open(newline="", encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def write_csv(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--input", default="eval_articles_with_gemini.csv")
    p.add_argument("--item-out", default="bertscore_by_item.csv")
    p.add_argument("--summary-out", default="bertscore_summary.csv")
    p.add_argument("--model", default="xlm-roberta-base")
    p.add_argument("--batch-size", type=int, default=8)
    args = p.parse_args()

    try:
        from bert_score import score
    except ImportError as exc:
        raise SystemExit("Install first: pip install bert-score") from exc

    rows = read_rows(Path(args.input))
    methods = [c for c in rows[0] if c.endswith("_summary") and c != "reference_summary"]
    item_rows = []

    for col in methods:
        pairs = [
            (r["eval_id"], r[col].strip(), r["reference_summary"].strip())
            for r in rows
            if r.get(col, "").strip() and r.get("reference_summary", "").strip()
        ]
        if not pairs:
            continue
        ids, preds, refs = zip(*pairs)
        p_vals, r_vals, f_vals = score(
            list(preds),
            list(refs),
            lang="vi",
            model_type=args.model,
            batch_size=args.batch_size,
            verbose=True,
        )
        for eval_id, p1, r1, f1 in zip(ids, p_vals, r_vals, f_vals):
            item_rows.append(
                {
                    "eval_id": eval_id,
                    "method": col.replace("_summary", ""),
                    "bertscore_p": float(p1),
                    "bertscore_r": float(r1),
                    "bertscore_f1": float(f1),
                }
            )

    if not item_rows:
        raise SystemExit("No BERTScore rows. Fill reference_summary and method summaries first.")

    agg: dict[str, dict[str, list[float]]] = defaultdict(lambda: defaultdict(list))
    for r in item_rows:
        for m in ["bertscore_p", "bertscore_r", "bertscore_f1"]:
            agg[r["method"]][m].append(float(r[m]))

    summary_rows = []
    for method, metrics in sorted(agg.items()):
        row = {"method": method, "n": len(metrics["bertscore_f1"])}
        for metric, values in metrics.items():
            row[metric] = sum(values) / len(values)
        summary_rows.append(row)

    write_csv(Path(args.item_out), item_rows)
    write_csv(Path(args.summary_out), summary_rows)
    print(f"Wrote {args.item_out}")
    print(f"Wrote {args.summary_out}")


if __name__ == "__main__":
    main()
