import os
import re
import unicodedata

os.environ.setdefault("MPLCONFIGDIR", "/tmp/matplotlib")

import joblib
import matplotlib.pyplot as plt
import pandas as pd
import seaborn as sns
from sklearn.metrics import accuracy_score, classification_report, confusion_matrix
from underthesea import word_tokenize

from model_registry import (
    build_models,
    resolve_model_artifact_path,
    resolve_tfidf_artifact_path,
)


DATA_PATH = "/home/binperdok/KLTN2026/Data/Test.csv"
RESULT_DIR = "src/ML/Result"
os.makedirs(RESULT_DIR, exist_ok=True)

LABEL_MAP = {
    0: "DEEP DIVE",
    1: "MARKET SIGNALS",
    2: "NOISE",
    3: "SOLUTIONS & USE CASES",
}
LABEL_ENC = {v: k for k, v in LABEL_MAP.items()}


def clean_text(text: str) -> str:
    text = unicodedata.normalize("NFC", str(text))
    text = text.lower()
    text = re.sub(r"http\S+|www\.\S+", " ", text)
    text = re.sub(r"\S+@\S+\.\S+", " ", text)
    text = re.sub(r"<.*?>", " ", text)
    text = re.sub(r"[^a-zA-ZÀ-ỹà-ỹ\s]", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def tokenize(text: str) -> str:
    return word_tokenize(text, format="text")


def ensure_text_tok(df: pd.DataFrame) -> pd.DataFrame:
    if "text_tok" in df.columns:
        return df

    df = df.copy()
    df["title"] = df["title"].fillna("") if "title" in df.columns else ""
    df["content"] = df["content"].fillna("") if "content" in df.columns else ""
    df["text"] = df["title"] + " " + df["title"] + " " + df["content"]
    df["text"] = df["text"].apply(clean_text)
    print("Tokenizing... (co the mat vai phut)")
    df["text_tok"] = df["text"].apply(tokenize)
    return df


def ensure_label_enc(df: pd.DataFrame) -> pd.DataFrame:
    if "label_enc" in df.columns:
        return df
    if "label" not in df.columns:
        raise ValueError("Test data must contain either label_enc or label.")

    df = df.copy()
    df["label_enc"] = df["label"].map(LABEL_ENC)
    if df["label_enc"].isna().any():
        missing = sorted(df.loc[df["label_enc"].isna(), "label"].dropna().unique())
        raise ValueError(f"Found labels outside LABEL_MAP: {missing}")
    return df


def main():
    tfidf_path = resolve_tfidf_artifact_path()
    if tfidf_path is None:
        raise FileNotFoundError(
            "Cannot find TF-IDF vectorizer. Expected "
            "src/ML/Training/tfidf_vectorizer.joblib or legacy .pkl"
        )

    print(f"Loading test data from: {DATA_PATH}")
    df = pd.read_csv(DATA_PATH)
    df = ensure_text_tok(df)
    df = ensure_label_enc(df)

    print(f"Loading TF-IDF vectorizer from: {tfidf_path}")
    tfidf = joblib.load(tfidf_path)
    X = tfidf.transform(df["text_tok"].fillna(""))
    y_true = df["label_enc"].astype(int)

    results_summary = {}
    for name in build_models():
        model_path = resolve_model_artifact_path(name)
        if model_path is None:
            print(f"\n[{name}] Model artifact not found -> skipping")
            continue

        print("\n" + "=" * 50)
        print(f"[{name}] Evaluating from: {model_path}")
        model = joblib.load(model_path)
        preds = model.predict(X)
        acc = accuracy_score(y_true, preds)
        results_summary[name] = acc
        present_labels = sorted(set(y_true) | set(preds))
        present_names = [LABEL_MAP[l] for l in present_labels]

        print(f"[{name}] Accuracy: {acc:.4f}")
        print(
            classification_report(
                y_true,
                preds,
                labels=present_labels,
                target_names=present_names,
                zero_division=0,
            )
        )

        cm = confusion_matrix(y_true, preds, labels=present_labels)
        fig, ax = plt.subplots(figsize=(7, 5))
        sns.heatmap(
            cm,
            annot=True,
            fmt="d",
            cmap="Blues",
            ax=ax,
            xticklabels=present_names,
            yticklabels=present_names,
        )
        ax.set_title(f"Confusion Matrix - {name}")
        ax.set_xlabel("Predicted")
        ax.set_ylabel("Actual")
        plt.tight_layout()
        cm_path = os.path.join(RESULT_DIR, f"evaluate_confusion_matrix_{name}.png")
        plt.savefig(cm_path)
        plt.close()
        print(f"[{name}] Confusion matrix saved -> {cm_path}")

    if results_summary:
        print("\n" + "=" * 50)
        print("EVALUATION SUMMARY")
        print("-" * 50)
        for name, acc in sorted(results_summary.items(), key=lambda x: -x[1]):
            print(f"  {name:<25} Accuracy: {acc:.4f}")
        print("=" * 50)


if __name__ == "__main__":
    main()
