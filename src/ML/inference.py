import pandas as pd
import joblib
import re
import unicodedata
import os
from underthesea import word_tokenize
from sklearn.metrics import classification_report, confusion_matrix, accuracy_score
import seaborn as sns
import matplotlib.pyplot as plt

RESULT_DIR = "src/ML/Result"
os.makedirs(RESULT_DIR, exist_ok=True)

def log(msg: str = ""):
    print(msg)

# ── Config ────────────────────────────────────────────────────────────────────
DATA_PATH  = "/home/binperdok/KLTN2026/Data/Test.csv"
TFIDF_PATH = "src/ML/Training/tfidf_vectorizer.pkl"
MODELS = {
    "LinearSVC":          "src/ML/Training/LinearSVC.pkl",
    "LogisticRegression": "src/ML/Training/LogisticRegression.pkl",
    "RandomForest":       "src/ML/Training/RandomForest.pkl",
}
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
tfidf = joblib.load(TFIDF_PATH)
X = tfidf.transform(df["text_tok"].fillna(""))
log(f"Feature matrix shape: {X.shape}")

if has_label:
    df["label_enc"] = df["label"].map(LABEL_ENC)
    y_true = df["label_enc"]
    log(f"\nLabel distribution:\n{df['label'].value_counts().to_string()}")

# ── Inference từng model ──────────────────────────────────────────────────────
results_summary = {}

for name, model_path in MODELS.items():
    log(f"\n{'='*50}")
    log(f"[{name}] Running inference...")
    model = joblib.load(model_path)
    preds = model.predict(X)
    df[f"pred_{name}"] = [LABEL_MAP.get(p, str(p)) for p in preds]

    if has_label:
        acc = accuracy_score(y_true, preds)
        present_labels = sorted(set(y_true))
        present_names  = [LABEL_MAP[l] for l in present_labels]
        report = classification_report(
            y_true, preds,
            labels=present_labels,
            target_names=present_names,
            zero_division=0,
        )
        results_summary[name] = acc
        log(f"[{name}] Accuracy: {acc:.4f}")
        log(f"[{name}] Classification Report:\n{report}")

        cm = confusion_matrix(y_true, preds, labels=present_labels)
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
out_cols = ["title", "label"] + [f"pred_{n}" for n in MODELS] if has_label \
           else ["title"] + [f"pred_{n}" for n in MODELS]
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
