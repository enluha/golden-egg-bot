from __future__ import annotations

from typing import Dict, List, Optional

import numpy as np
import pandas as pd


def _sigmoid(z: np.ndarray) -> np.ndarray:
    return 1.0 / (1.0 + np.exp(-z))


class LogisticScorer:
    """Minimal logistic regression with L2 regularisation."""

    def __init__(
        self,
        feature_cols: List[str],
        l2: float = 1e-2,
        max_iter: int = 500,
        lr: float = 0.05,
    ) -> None:
        self.feature_cols = feature_cols
        self.l2 = l2
        self.max_iter = max_iter
        self.lr = lr
        self.w: Optional[np.ndarray] = None
        self.b: float = 0.0

    def fit(self, df: pd.DataFrame, label_col: str = "label") -> None:
        X = df[self.feature_cols].astype(float).fillna(0.0).to_numpy()
        y = df[label_col].astype(float).to_numpy()
        if X.size == 0:
            raise ValueError("Training data is empty")
        n, d = X.shape
        w = np.zeros(d, dtype=float)
        b = 0.0
        for _ in range(self.max_iter):
            z = X @ w + b
            p = _sigmoid(z)
            err = p - y
            grad_w = X.T @ err / n + self.l2 * w
            grad_b = float(err.mean())
            w -= self.lr * grad_w
            b -= self.lr * grad_b
        self.w = w
        self.b = b

    def predict_proba(self, feats: Dict[str, float]) -> float:
        if self.w is None:
            raise ValueError("Model not fitted")
        x = np.array([float(feats.get(c, 0.0) or 0.0) for c in self.feature_cols], dtype=float)
        z = float(x @ self.w + self.b)
        return float(_sigmoid(np.array([z]))[0])

    @staticmethod
    def make_training_frame(trades: pd.DataFrame, feature_cols: List[str]) -> pd.DataFrame:
        df = trades.copy()
        df = df[df["exit_reason"].isin(["target", "stop"])].copy()
        df["label"] = (df["exit_reason"] == "target").astype(int)
        for col in feature_cols:
            if col not in df.columns:
                df[col] = 0.0
        cols = feature_cols + ["label"]
        return df[cols]
