import pandas as pd
import joblib
import logging
import time
import os
from datetime import datetime
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.svm import LinearSVC
from sklearn.linear_model import LogisticRegression
from sklearn.ensemble import RandomForestClassifier
from sklearn.model_selection import train_test_split
# Bổ sung Pipeline
from sklearn.pipeline import Pipeline 
from sklearn.metrics import classification_report, accuracy_score

LOG_DIR = "src/ML/Training"
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
# Đường dẫn dữ liệu của bạn
df = pd.read_csv(r"C:\Phuc\KLTN\Data\PROCESSED_DATA.csv")
X = df['text_tok'].fillna('')
y = df['label_enc']
logger.info(f"Total samples: {len(df)} | Classes: {sorted(y.unique())}")
logger.info(f"Label distribution:\n{df['label'].value_counts().to_string()}")

# --- Split ---
X_train, X_test, y_train, y_test = train_test_split(
    X, y, test_size=0.2, random_state=42, stratify=y
)
logger.info(f"Train: {len(X_train)} | Test: {len(X_test)}")

# --- Định nghĩa các tham số mô hình ---
models = {
    "LinearSVC":          LinearSVC(max_iter=2000, random_state=42),
    "LogisticRegression": LogisticRegression(max_iter=1000, random_state=42),
    "RandomForest":       RandomForestClassifier(n_estimators=200, random_state=42),
}

results = {}
best_acc = 0
best_model_name = ""
best_pipeline = None

# --- Train bằng Pipeline ---
for name, clf in models.items():
    logger.info(f"[{name}] Training started...")
    t0 = time.time()
    
    # Đóng gói TF-IDF và Classifier vào 1 Pipeline
    pipeline = Pipeline([
        ('tfidf', TfidfVectorizer(ngram_range=(1, 2), max_features=30000)),
        ('classifier', clf)
    ])

    # Fit trực tiếp raw text
    pipeline.fit(X_train, y_train)
    elapsed = time.time() - t0

    # Predict trực tiếp raw text
    preds = pipeline.predict(X_test)
    acc   = accuracy_score(y_test, preds)
    report = classification_report(y_test, preds)

    results[name] = acc
    logger.info(f"[{name}] Done in {elapsed:.2f}s | Accuracy: {acc:.4f}")
    logger.info(f"[{name}] Classification Report:\n{report}")
    
    # Lưu pipeline dự phòng nếu muốn kiểm tra cục bộ
    # local_path = os.path.join(LOG_DIR, f"{name}_pipeline.joblib")
    # joblib.dump(pipeline, local_path)

    # Cập nhật mô hình tốt nhất
    if acc > best_acc:
        best_acc = acc
        best_model_name = name
        best_pipeline = pipeline

# --- LƯU DUY NHẤT 1 FILE CHO VERTEX AI ---
vertex_model_path = os.path.join(LOG_DIR, "model.joblib")
joblib.dump(best_pipeline, vertex_model_path)
logger.info(f"[*] BEST MODEL ({best_model_name}) saved for Vertex AI -> {vertex_model_path}")

# --- Tóm tắt kết quả ---
logger.info("=" * 50)
logger.info("SUMMARY")
for name, acc in sorted(results.items(), key=lambda x: -x[1]):
    logger.info(f"  {name:<25} Accuracy: {acc:.4f}")
logger.info(f"Log saved -> {log_path}")
logger.info("=" * 50)