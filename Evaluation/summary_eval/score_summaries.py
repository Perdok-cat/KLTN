#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import re
from collections import defaultdict
from pathlib import Path


def tokens(text: str) -> list[str]:
    return re.findall(r"[0-9A-Za-zÀ-ỹà-ỹ]+", (text or "").lower())


def ngrams(xs: list[str], n: int) -> list[tuple[str, ...]]:
    return [tuple(xs[i : i + n]) for i in range(max(0, len(xs) - n + 1))]


def f1(overlap: int, pred_total: int, ref_total: int) -> float:
    if overlap == 0 or pred_total == 0 or ref_total == 0:
        return 0.0
    p = overlap / pred_total
    r = overlap / ref_total
    return 2 * p * r / (p + r)


def rouge_n(pred: str, ref: str, n: int) -> float:
    from collections import Counter

    pred_ng = Counter(ngrams(tokens(pred), n))
    ref_ng = Counter(ngrams(tokens(ref), n))
    overlap = sum((pred_ng & ref_ng).values())
    return f1(overlap, sum(pred_ng.values()), sum(ref_ng.values()))


def lcs_len(a: list[str], b: list[str]) -> int:
    dp = [0] * (len(b) + 1)
    for x in a:
        prev = 0
        for j, y in enumerate(b, 1):
            cur = dp[j]
            dp[j] = prev + 1 if x == y else max(dp[j], dp[j - 1])
            prev = cur
    return dp[-1]


def rouge_l(pred: str, ref: str) -> float:
    pt, rt = tokens(pred), tokens(ref)
    return f1(lcs_len(pt, rt), len(pt), len(rt))


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
    p.add_argument("--item-out", default="automatic_scores_by_item.csv")
    p.add_argument("--summary-out", default="automatic_scores_summary.csv")
    args = p.parse_args()

    rows = read_rows(Path(args.input))
    methods = [c for c in rows[0] if c.endswith("_summary") and c != "reference_summary"]
    item_scores = []
    for r in rows:
        ref = r.get("reference_summary", "").strip()
        if not ref:
            continue
        for m in methods:
            pred = r.get(m, "").strip()
            if not pred:
                continue
            item_scores.append(
                {
                    "eval_id": r["eval_id"],
                    "method": m.replace("_summary", ""),
                    "rouge_1": rouge_n(pred, ref, 1),
                    "rouge_2": rouge_n(pred, ref, 2),
                    "rouge_l": rouge_l(pred, ref),
                }
            )

    if not item_scores:
        raise SystemExit("No scores. Fill reference_summary and method summaries first.")

    agg: dict[str, dict[str, list[float]]] = defaultdict(lambda: defaultdict(list))
    for s in item_scores:
        for metric in ["rouge_1", "rouge_2", "rouge_l"]:
            agg[s["method"]][metric].append(float(s[metric]))

    summary_rows = []
    for method, metrics in sorted(agg.items()):
        row = {"method": method, "n": len(metrics["rouge_1"])}
        for metric, values in metrics.items():
            row[metric] = sum(values) / len(values)
        summary_rows.append(row)

    write_csv(Path(args.item_out), item_scores)
    write_csv(Path(args.summary_out), summary_rows)
    print(f"Wrote {args.item_out}")
    print(f"Wrote {args.summary_out}")


if __name__ == "__main__":
    main()
