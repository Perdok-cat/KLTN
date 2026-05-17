import pandas as pd
import joblib
import re
import unicodedata
import os
from underthesea import word_tokenize
from sklearn.metrics import classification_report, confusion_matrix, accuracy_score

os.environ.setdefault("MPLCONFIGDIR", "/tmp/matplotlib")
import seaborn as sns
import matplotlib.pyplot as plt

from model_registry import (
    build_models,
    resolve_model_artifact_path,
    resolve_tfidf_artifact_path,
)

RESULT_DIR = "src/ML/Result"
os.makedirs(RESULT_DIR, exist_ok=True)

def log(msg: str = ""):
    print(msg)

# ── Config ────────────────────────────────────────────────────────────────────
DATA_PATH  = "/home/binperdok/KLTN2026/Data/Test.csv"
MODEL_NAMES = list(build_models().keys())
LABEL_MAP = {
    0: "DEEP DIVE",
    1: "MARKET SIGNALS",
    2: "NOISE",
    3: "SOLUTIONS & USE CASES",
}
LABEL_ENC = {v: k for k, v in LABEL_MAP.items()}

# ── Preprocessing ─────────────────────────────────────────────────────────────
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

def preprocess(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df["title"]   = df["title"].fillna("")
    df["content"] = df["content"].fillna("")
    df["text"]    = df["title"] + " " + df["title"] + " " + df["content"]
    df["text"]    = df["text"].apply(clean_text)
    log("Tokenizing... (có thể mất vài phút)")
    df["text_tok"] = df["text"].apply(tokenize)
    return df

# ── Load data ─────────────────────────────────────────────────────────────────
log(f"Loading test data from: {DATA_PATH}")
df = pd.read_csv(DATA_PATH)
log(f"Raw test samples  : {len(df)}")
log(f"Columns           : {list(df.columns)}")

has_label = "label" in df.columns and df["label"].notna().any()

df = preprocess(df)
log(f"Preprocessing done. Sample text_tok:\n  {df['text_tok'].iloc[0][:200]}")

# ── Load TF-IDF ───────────────────────────────────────────────────────────────
log("\nLoading TF-IDF vectorizer...")
tfidf_path = resolve_tfidf_artifact_path()
if tfidf_path is None:
    raise FileNotFoundError(
        "Cannot find TF-IDF vectorizer. Expected "
        "src/ML/Training/tfidf_vectorizer.joblib or legacy .pkl"
    )
log(f"TF-IDF path: {tfidf_path}")
tfidf = joblib.load(tfidf_path)
X = tfidf.transform(df["text_tok"].fillna(""))
log(f"Feature matrix shape: {X.shape}")

if has_label:
    df["label_enc"] = df["label"].map(LABEL_ENC)
    y_true = df["label_enc"]
    valid_label_mask = y_true.notna()
    log(f"\nLabel distribution:\n{df['label'].value_counts().to_string()}")

# ── Inference từng model ──────────────────────────────────────────────────────
results_summary = {}
available_models = []

for name in MODEL_NAMES:
    model_path = resolve_model_artifact_path(name)
    if model_path is None:
        log(f"\n[{name}] Model artifact not found -> skipping")
        continue

    available_models.append(name)
    log(f"\n{'='*50}")
    log(f"[{name}] Running inference from: {model_path}")
    model = joblib.load(model_path)
    preds = model.predict(X)
    df[f"pred_{name}"] = [LABEL_MAP.get(p, str(p)) for p in preds]

    if has_label:
        y_eval = y_true[valid_label_mask].astype(int)
        preds_eval = preds[valid_label_mask]
        acc = accuracy_score(y_eval, preds_eval)
        present_labels = sorted(set(y_eval) | set(preds_eval))
        present_names  = [LABEL_MAP[l] for l in present_labels]
        report = classification_report(
            y_eval, preds_eval,
            labels=present_labels,
            target_names=present_names,
            zero_division=0,
        )
        results_summary[name] = acc
        log(f"[{name}] Accuracy: {acc:.4f}")
        log(f"[{name}] Classification Report:\n{report}")

        cm = confusion_matrix(y_eval, preds_eval, labels=present_labels)
        fig, ax = plt.subplots(figsize=(7, 5))
        sns.heatmap(
            cm, annot=True, fmt="d", cmap="Blues", ax=ax,
            xticklabels=present_names,
            yticklabels=present_names,
        )
        ax.set_title(f"Confusion Matrix — {name}")
        ax.set_xlabel("Predicted")
        ax.set_ylabel("Actual")
        plt.tight_layout()
        cm_path = os.path.join(RESULT_DIR, f"confusion_matrix_{name}.png")
        plt.savefig(cm_path)
        plt.close()
        log(f"[{name}] Confusion matrix saved -> {cm_path}")
    else:
        log(f"[{name}] No ground-truth label → skipping metrics")

# ── Lưu kết quả suy luận ─────────────────────────────────────────────────────
out_cols = ["title", "label"] + [f"pred_{n}" for n in available_models] if has_label \
           else ["title"] + [f"pred_{n}" for n in available_models]
out_path = os.path.join(RESULT_DIR, "inference_result.csv")
df[out_cols].to_csv(out_path, index=False)
log(f"\nInference results saved -> {out_path}")

# ── Summary ───────────────────────────────────────────────────────────────────
if has_label and results_summary:
    log("\n" + "="*50)
    log("INFERENCE SUMMARY")
    log("-"*50)
    for name, acc in sorted(results_summary.items(), key=lambda x: -x[1]):
        log(f"  {name:<25} Accuracy: {acc:.4f}")
    log("="*50)
