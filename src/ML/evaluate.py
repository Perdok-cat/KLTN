import pandas as pd
import joblib
from sklearn.metrics import classification_report, confusion_matrix
import seaborn as sns
import matplotlib.pyplot as plt

tfidf = joblib.load("src/ML/Training/tfidf_vectorizer.pkl")
model = joblib.load("src/ML/Training/LinearSVC.pkl")  # đổi tên model muốn test

df = pd.read_csv("/home/binperdok/KLTN2026/Data/Test.csv")
X = tfidf.transform(df['text_tok'].fillna(''))
y = df['label_enc']

preds = model.predict(X)
print(classification_report(y, preds))

cm = confusion_matrix(y, preds)
sns.heatmap(cm, annot=True, fmt='d')
plt.tight_layout()
plt.savefig("src/ML/Training/confusion_matrix.png")