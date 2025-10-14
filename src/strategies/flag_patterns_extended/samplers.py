from __future__ import annotations

import random
from typing import Any, Dict, Iterable, List, Union

Number = Union[int, float]
GridSpec = Dict[str, Iterable[Any]]


def _is_range(x: Any) -> bool:
    return isinstance(x, tuple) and len(x) == 2 and all(isinstance(v, (int, float)) for v in x)


def _cast_like(val: float, ref: Any) -> Any:
    return int(round(val)) if isinstance(ref, int) else float(val)


def latin_hypercube(grid: GridSpec, n: int, seed: int = 42) -> List[Dict[str, Any]]:
    """
    Latin-hypercube over a dict where each value is either:
      - a list of discrete options, or
      - a tuple(min,max) treated as a continuous range
    Returns n samples (dicts).
    """
    rnd = random.Random(seed)
    keys = list(grid.keys())
    strata: Dict[str, List[Any]] = {}
    for key in keys:
        spec = grid[key]
        if _is_range(spec):
            lo, hi = spec  # type: ignore[arg-type]
            bins = [(i + rnd.random()) / n for i in range(n)]
            vals = [lo + (hi - lo) * u for u in bins]
            strata[key] = vals
        else:
            opts = list(spec)
            if len(opts) >= n:
                pool = opts.copy()
                rnd.shuffle(pool)
                vals: List[Any] = []
                for _ in range(n):
                    if not pool:
                        pool = opts.copy()
                        rnd.shuffle(pool)
                    vals.append(pool.pop())
            else:
                reps = (n + len(opts) - 1) // len(opts) if opts else 1
                vals = (opts * reps)[:n] if opts else [None] * n
                rnd.shuffle(vals)
            strata[key] = vals

    for key in keys:
        rnd.shuffle(strata[key])

    rows: List[Dict[str, Any]] = []
    for i in range(n):
        row = {key: strata[key][i] for key in keys}
        rows.append(row)
    return rows


def random_samples(grid: GridSpec, n: int, seed: int = 42) -> List[Dict[str, Any]]:
    """
    Simple random sampler. Same spec semantics as LHS.
    """
    rnd = random.Random(seed)
    keys = list(grid.keys())
    rows: List[Dict[str, Any]] = []
    for _ in range(n):
        row: Dict[str, Any] = {}
        for key in keys:
            spec = grid[key]
            if _is_range(spec):
                lo, hi = spec  # type: ignore[arg-type]
                u = rnd.random()
                val = lo + (hi - lo) * u
                row[key] = _cast_like(val, lo if isinstance(lo, int) else hi)
            else:
                opts = list(spec)
                row[key] = rnd.choice(opts) if opts else None
        rows.append(row)
    return rows
