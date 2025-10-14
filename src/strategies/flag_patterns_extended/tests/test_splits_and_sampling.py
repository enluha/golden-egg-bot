from __future__ import annotations

import numpy as np

from ..samplers import latin_hypercube
from ..splits import anchored_walk_forward, purged_kfold_indices


def test_purged_kfold_no_overlap() -> None:
    n = 1000
    splits = purged_kfold_indices(n, n_splits=5, purge=10, embargo=10)
    for split in splits:
        assert len(set(split.train_idx).intersection(set(split.test_idx))) == 0


def test_anchored_walk_forward_grows() -> None:
    n = 1000
    splits = anchored_walk_forward(n, test_size=100, step=100, min_train=200, purge=5, embargo=10)
    assert len(splits) >= 1
    assert all(len(split.test_idx) == 100 for split in splits)


def test_latin_hypercube_shapes() -> None:
    grid = {"a": (0.0, 1.0), "b": [1, 2, 3, 4]}
    rows = latin_hypercube(grid, n=16, seed=7)
    assert len(rows) == 16
    assert all(set(row.keys()) == {"a", "b"} for row in rows)
