#!/usr/bin/env python3
"""Reference solution: a compact 20-newsgroups topic classifier.

The size constraint is what makes this hard. A full TF-IDF + linear model is
~18 MB; capping the vocabulary by frequency loses too much accuracy. The trick
is to (1) select the most class-informative terms with a chi-squared test,
(2) rebuild the vectorizer with ONLY those terms as its vocabulary so the
pickled vocab stays small (a plain SelectKBest after a full vectorizer still
pickles the whole vocabulary), and (3) store the linear weights as float32.
That lands ~0.69 accuracy in under 1 MiB.
"""
import json
import pickle
import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.svm import LinearSVC
from sklearn.feature_selection import SelectKBest, chi2
from sklearn.pipeline import Pipeline

TRAIN = "/app/data/train.jsonl"
OUT = "/app/model.pkl"


def load(path):
    texts, labels = [], []
    with open(path) as f:
        for line in f:
            o = json.loads(line)
            texts.append(o["text"])
            labels.append(o["label"])
    return texts, labels


def main():
    texts, labels = load(TRAIN)
    base = TfidfVectorizer(sublinear_tf=True, min_df=2)
    Xtr = base.fit_transform(texts)
    support = SelectKBest(chi2, k=9000).fit(Xtr, labels).get_support()
    vocab = {f: i for i, f in enumerate(np.asarray(base.get_feature_names_out())[support])}

    pipe = Pipeline([
        ("vec", TfidfVectorizer(sublinear_tf=True, vocabulary=vocab)),
        ("clf", LinearSVC(C=0.3, random_state=0)),
    ]).fit(texts, labels)

    clf = pipe.named_steps["clf"]
    clf.coef_ = clf.coef_.astype(np.float32)
    clf.intercept_ = clf.intercept_.astype(np.float32)

    with open(OUT, "wb") as f:
        pickle.dump(pipe, f)


if __name__ == "__main__":
    main()
