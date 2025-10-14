"""
Refactored Flag & Pennant detector (no lookahead).
Delegates core work to detector.py and consumes a Config object.

Usage:
    from .config import Config
    from .flags_pennants import find_flag_pennant_patterns

    cfg = Config()  # or Config.from_yaml("params_default.yaml")
    patterns = find_flag_pennant_patterns(df, cfg)
"""

from __future__ import annotations
from typing import List
import pandas as pd
from .config import Config
from .detector import detect_patterns, DetectedPattern


def find_flag_pennant_patterns(
    df: pd.DataFrame,
    cfg: Config,
    *,
    price_col: str = "close",
) -> List[DetectedPattern]:
    """
    Compatibility-friendly wrapper. Returns a list of DetectedPattern
    (contains pole, consolidation, boundary lines, type, and geometry features).
    """
    return detect_patterns(df=df, cfg=cfg, price_col=price_col)
