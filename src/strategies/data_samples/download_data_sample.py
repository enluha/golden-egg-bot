"""Utility to download OHLCV samples from Binance and save them to CSV.

Example usage:
    python download_data_sample.py --symbol BTCUSDT --interval 3600 \
        --start "2018-06-01" --end "2020-07-01"
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import sys
import time
from pathlib import Path
from typing import Dict, Iterable, List

import requests

# Common symbols for future use: ETHUSDT, BNBUSDT, SOLUSDT, XRPUSDT, ADAUSDT.

# Default fetch parameters; adjust to test other pairs or windows.
DEFAULT_SYMBOL = "BTCUSDT"
DEFAULT_INTERVAL_SECONDS = 3600
DEFAULT_START_DATE = "2024-06-10"   # YYYY-MM-DD
DEFAULT_END_DATE = "2025-10-12"
DEFAULT_OUTPUT_DIR = Path(__file__).resolve().parent

BINANCE_KLINES_URL = "https://api.binance.com/api/v3/klines"
INTERVAL_MAP: Dict[int, str] = {
    60: "1m",
    180: "3m",
    300: "5m",
    900: "15m",
    1800: "30m",
    3600: "1h",
    7200: "2h",
    14400: "4h",
    21600: "6h",
    28800: "8h",
    43200: "12h",
    86400: "1d",
    259200: "3d",
    604800: "1w",
    2592000: "1M",
}

DATE_OUTPUT_FMT = "%d/%m/%Y %H:%M"


def daterange_batches(start: dt.datetime, end: dt.datetime, interval_seconds: int) -> Iterable[int]:
    """Yield timestamps (ms) for Binance pagination."""

    current = start
    while current < end:
        yield int(current.timestamp() * 1000)
        # Binance allows up to 1000 candles per query
        current += dt.timedelta(seconds=interval_seconds * 1000)


def fetch_klines(symbol: str, interval: str, start_ms: int, end_ms: int) -> List[List]:
    """Fetch klines from Binance, handling simple retry logic."""

    params = {
        "symbol": symbol.upper(),
        "interval": interval,
        "startTime": start_ms,
        "endTime": end_ms,
        "limit": 1000,
    }
    retries = 3
    for attempt in range(1, retries + 1):
        response = requests.get(BINANCE_KLINES_URL, params=params, timeout=30)
        if response.status_code == 429:
            time.sleep(1.0 * attempt)
            continue
        response.raise_for_status()
        data = response.json()
        if not data:
            return []
        return data
    raise RuntimeError("Failed to fetch klines from Binance after retries")


def parse_args(argv: List[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Download OHLCV samples from Binance")
    parser.add_argument(
        "--symbol",
        default=DEFAULT_SYMBOL,
        help=f"Trading pair symbol (default: {DEFAULT_SYMBOL})",
    )
    parser.add_argument(
        "--interval",
        type=int,
        default=DEFAULT_INTERVAL_SECONDS,
        help="Candle interval in seconds (e.g. 3600 for 1h, 86400 for 1d)",
    )
    parser.add_argument(
        "--start",
        default=DEFAULT_START_DATE,
        help="Start date (YYYY-MM-DD). Binance timestamps are UTC.",
    )
    parser.add_argument(
        "--end",
        default=DEFAULT_END_DATE,
        help="End date (YYYY-MM-DD). End is exclusive.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_OUTPUT_DIR,
        help="Where to write the CSV (default: data_samples directory).",
    )
    return parser.parse_args(argv)


def ensure_interval(interval_seconds: int) -> str:
    if interval_seconds not in INTERVAL_MAP:
        available = ", ".join(str(k) for k in sorted(INTERVAL_MAP))
        raise ValueError(f"Unsupported interval {interval_seconds}. Choose from: {available}")
    return INTERVAL_MAP[interval_seconds]


def format_filename(symbol: str, interval_seconds: int, start: dt.datetime, end: dt.datetime) -> str:
    start_tag = start.strftime("%b%Y")
    end_tag = end.strftime("%b%Y")
    return f"{symbol.upper()}{interval_seconds}_{start_tag}_{end_tag}.csv"


def save_csv(rows: List[List], path: Path) -> None:
    header = ["date", "close", "open", "high", "low"]
    # Optional extra columns from Binance spot/futures klines.
    # Uncomment entries in `header` AND the matching field in the writerow block below
    # to include them in the CSV.
    # header.extend([
    #     "volume",  # base asset volume
    #     "quote_volume",  # quote asset volume
    #     "close_time",
    #     "number_of_trades",
    #     "taker_buy_volume",
    #     "taker_buy_quote_volume",
    # ])
    with path.open("w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(header)
        for row in rows:
            open_time = dt.datetime.utcfromtimestamp(row[0] / 1000)
            formatted_time = open_time.strftime(DATE_OUTPUT_FMT)
            output_row = [
                formatted_time,
                row[4],  # close
                row[1],  # open
                row[2],  # high
                row[3],  # low
            ]
            # Optional fields (indices per Binance API spec):
            # output_row.append(row[5])   # volume
            # output_row.append(row[7])   # quote asset volume
            # output_row.append(dt.datetime.utcfromtimestamp(row[6] / 1000).strftime(DATE_OUTPUT_FMT))  # close time
            # output_row.append(row[8])   # number of trades
            # output_row.append(row[9])   # taker buy base volume
            # output_row.append(row[10])  # taker buy quote volume
            writer.writerow(output_row)


def main(argv: List[str]) -> None:
    args = parse_args(argv)
    interval_code = ensure_interval(args.interval)

    start_dt = dt.datetime.strptime(args.start, "%Y-%m-%d").replace(tzinfo=dt.timezone.utc)
    end_dt = dt.datetime.strptime(args.end, "%Y-%m-%d").replace(tzinfo=dt.timezone.utc)
    if start_dt >= end_dt:
        raise ValueError("Start date must precede end date")

    output_dir = args.output_dir
    output_dir.mkdir(parents=True, exist_ok=True)
    output_file = output_dir / format_filename(args.symbol, args.interval, start_dt, end_dt)
    if output_file.exists():
        print(f"Overwriting existing file at {output_file}")

    all_rows: List[List] = []
    start_ms = int(start_dt.timestamp() * 1000)
    end_ms = int(end_dt.timestamp() * 1000)

    current = start_ms
    while current < end_ms:
        chunk = fetch_klines(args.symbol, interval_code, current, end_ms)
        if not chunk:
            break
        all_rows.extend(chunk)
        current = int(chunk[-1][0]) + args.interval * 1000
        time.sleep(0.25)

    if not all_rows:
        raise RuntimeError("No data returned; check symbol, interval, or date range")

    save_csv(all_rows, output_file)
    print(f"Saved {len(all_rows)} candles to {output_file}")


if __name__ == "__main__":
    main(sys.argv[1:])
