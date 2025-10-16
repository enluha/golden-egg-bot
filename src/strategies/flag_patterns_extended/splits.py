from __future__ import annotations

from dataclasses import dataclass
from typing import List

import numpy as np


@dataclass(frozen=True)
class Split:
    train_idx: np.ndarray
    test_idx: np.ndarray


def purged_kfold_indices(
    n: int,
    n_splits: int = 5,
    purge: int = 0,
    embargo: int = 0,
) -> List[Split]:
    """
    Lopez de Prado style purged k-fold.
    """
    if n_splits < 2:
        raise ValueError("n_splits must be >= 2")
    fold_sizes = np.full(n_splits, n // n_splits, dtype=int)
    fold_sizes[: n % n_splits] += 1
    bounds = np.concatenate([[0], np.cumsum(fold_sizes)])

    indices = np.arange(n)
    splits: List[Split] = []
    for k in range(n_splits):
        a, b = bounds[k], bounds[k + 1]
        test = indices[a:b]
        mask = np.ones(n, dtype=bool)
        purge_left = max(0, a - purge)
        embargo_right = min(n, b + embargo)
        mask[purge_left:embargo_right] = False
        train = indices[mask]
        splits.append(Split(train_idx=train, test_idx=test))
    return splits


def anchored_walk_forward(
    n: int,
    test_size: int,
    step: int,
    *,
    min_train: int = 200,
    purge: int = 0,
    embargo: int = 0,
) -> List[Split]:
    """
    Anchored expanding window with purge/embargo.
    """
    if n <= 0:
        return []
    splits: List[Split] = []
    anchor = max(min_train, 1)
    while anchor + test_size <= n:
        a, b = anchor, anchor + test_size
        test = np.arange(a, b)
        train_end = max(0, a - purge)
        train = np.arange(0, train_end)
        splits.append(Split(train_idx=train, test_idx=test))
        anchor = anchor + step + embargo
    return splits


def render_split_timeline(n: int, splits: List[Split], *, char_train: str = "T", char_test: str = "W", char_none: str = "0", max_len: int = 120) -> str:
    """
    Render a compact ASCII timeline like [TTTTTWW0000TTW000TTWW].
    - Total length approximates n (sample size), clipped to max_len for long series.
    - T marks indices used in any train set, W in any test set, 0 otherwise.
    - If an index is both in train and test across different splits, W wins (test visibility).
    """
    if n <= 0:
        return "[]"
    # Downsample indices if n is large
    L = min(n, max_len)
    scale = n / L
    train_mask = np.zeros(L, dtype=bool)
    test_mask = np.zeros(L, dtype=bool)
    for sp in splits or []:
        if sp.train_idx.size:
            idx = np.clip((sp.train_idx / scale).astype(int), 0, L - 1)
            train_mask[idx] = True
        if sp.test_idx.size:
            idx = np.clip((sp.test_idx / scale).astype(int), 0, L - 1)
            test_mask[idx] = True
    chars = []
    for i in range(L):
        if test_mask[i]:
            chars.append(char_test)
        elif train_mask[i]:
            chars.append(char_train)
        else:
            chars.append(char_none)
    return "[" + "".join(chars) + "]"
