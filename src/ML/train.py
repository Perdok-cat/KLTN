import pandas as pd
import joblib
import logging
import time
import os
from datetime import datetime
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.model_selection import train_test_split
from sklearn.metrics import classification_report, accuracy_score

from model_registry import (
    TFIDF_FILENAME,
    TRAINING_DIR,
    build_models,
    model_artifact_path,
)

LOG_DIR = TRAINING_DIR
os.makedirs(LOG_DIR, exist_ok=True)

log_path = os.path.join(LOG_DIR, f"train_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log")
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[
        logging.FileHandler(log_path, encoding="utf-8"),
        logging.StreamHandler(),
    ],
)
logger = logging.getLogger(__name__)

# --- Load data ---
logger.info("Loading data...")
df = pd.read_csv("/home/binperdok/KLTN2026/Data/PROCESSED_DATA.csv")
X = df['text_tok'].fillna('')
y = df['label_enc']
logger.info(f"Total samples: {len(df)} | Classes: {sorted(y.unique())}")
logger.info(f"Label distribution:\n{df['label'].value_counts().to_string()}")

# --- Split ---
X_train, X_test, y_train, y_test = train_test_split(
    X, y, test_size=0.2, random_state=42, stratify=y
)
logger.info(f"Train: {len(X_train)} | Test: {len(X_test)}")

# --- TF-IDF ---
logger.info("Fitting TF-IDF vectorizer (ngram 1-2, max_features=30000)...")
t0 = time.time()
tfidf = TfidfVectorizer(ngram_range=(1, 2), max_features=30000)
X_train_vec = tfidf.fit_transform(X_train)
X_test_vec  = tfidf.transform(X_test)
logger.info(f"TF-IDF done in {time.time() - t0:.2f}s | Vocab size: {len(tfidf.vocabulary_)}")

# --- Train nhiều mô hình ---
models = build_models()

results = {}

for name, model in models.items():
    logger.info(f"[{name}] Training started...")
    t0 = time.time()
    model.fit(X_train_vec, y_train)
    elapsed = time.time() - t0

    preds = model.predict(X_test_vec)
    acc   = accuracy_score(y_test, preds)
    report = classification_report(y_test, preds)

    results[name] = acc
    logger.info(f"[{name}] Done in {elapsed:.2f}s | Accuracy: {acc:.4f}")
    logger.info(f"[{name}] Classification Report:\n{report}")

    model_path = model_artifact_path(name)
    joblib.dump(model, model_path)
    logger.info(f"[{name}] Model saved -> {model_path}")

# --- Lưu vectorizer ---
vec_path = os.path.join(LOG_DIR, TFIDF_FILENAME)
joblib.dump(tfidf, vec_path)
logger.info(f"Vectorizer saved -> {vec_path}")

# --- Tóm tắt kết quả ---
logger.info("=" * 50)
logger.info("SUMMARY")
for name, acc in sorted(results.items(), key=lambda x: -x[1]):
    logger.info(f"  {name:<25} Accuracy: {acc:.4f}")
logger.info(f"Log saved -> {log_path}")
logger.info("=" * 50)
