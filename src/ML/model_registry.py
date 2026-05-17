import os

from sklearn.ensemble import RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.neighbors import KNeighborsClassifier
from sklearn.naive_bayes import BernoulliNB, ComplementNB, MultinomialNB
from sklearn.svm import LinearSVC
from sklearn.tree import DecisionTreeClassifier


RANDOM_STATE = 42
TRAINING_DIR = "src/ML/Training"
TFIDF_FILENAME = "tfidf_vectorizer.joblib"
LEGACY_TFIDF_FILENAME = "tfidf_vectorizer.pkl"


def build_models():
    return {
        "LinearSVC": LinearSVC(max_iter=2000, random_state=RANDOM_STATE),
        "LogisticRegression": LogisticRegression(
            max_iter=1000,
            random_state=RANDOM_STATE,
        ),
        "MultinomialNB": MultinomialNB(),
        "ComplementNB": ComplementNB(),
        "BernoulliNB": BernoulliNB(),
        "DecisionTree": DecisionTreeClassifier(
            random_state=RANDOM_STATE,
        ),
        "RandomForest": RandomForestClassifier(
            n_estimators=200,
            random_state=RANDOM_STATE,
        ),
        "KNeighbors": KNeighborsClassifier(
            n_neighbors=5,
        ),
    }


def model_artifact_path(model_name, extension=".joblib"):
    return os.path.join(TRAINING_DIR, f"{model_name}{extension}")


def resolve_model_artifact_path(model_name):
    paths = [
        model_artifact_path(model_name, ".joblib"),
        model_artifact_path(model_name, ".pkl"),
    ]
    for path in paths:
        if os.path.exists(path):
            return path
    return None


def resolve_tfidf_artifact_path():
    paths = [
        os.path.join(TRAINING_DIR, TFIDF_FILENAME),
        os.path.join(TRAINING_DIR, LEGACY_TFIDF_FILENAME),
    ]
    for path in paths:
        if os.path.exists(path):
            return path
    return None
