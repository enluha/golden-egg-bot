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
