#!/usr/bin/env python
from __future__ import annotations

from pathlib import Path

seed = 0x12345

def rnd() -> float:
    global seed
    seed = (1103515245 * seed + 12345) & 0x7FFFFFFF
    return seed / 0x7FFFFFFF

rows = 500
base_ts = 1640995200
current = 30000.0

lines = ["date,open,high,low,close\n"]
for i in range(rows):
    drift = (rnd() - 0.5) * 0.01
    volatility = 0.01 + rnd() * 0.01
    open_price = current * (1 + drift * 0.1)
    high_price = open_price * (1 + abs(drift) * volatility)
    low_price = open_price * (1 - abs(drift) * volatility)
    close_price = open_price * (1 + drift)
    current = close_price
    ts = base_ts + i * 3600
    lines.append(f"{ts},{open_price:.2f},{high_price:.2f},{low_price:.2f},{close_price:.2f}\n")

Path("sample.csv").write_text("".join(lines))
