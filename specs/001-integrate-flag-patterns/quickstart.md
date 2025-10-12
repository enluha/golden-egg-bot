# Quickstart – Flag Patterns Strategy Integration

## Prerequisites
- Python toolchain managed via `uv` located at `/home/kiluh/.local/bin/uv`.
- Use the existing project virtual environment `venvTrading/` for all commands.
- Historical data accessible via GoldenEggBot data loaders or sample CSVs (e.g., `BTCUSDT3600.csv`).

## Environment Setup
```bash
# from repo root
/home/kiluh/.local/bin/uv pip install --python venvTrading/bin/python -r requirements.txt
/home/kiluh/.local/bin/uv pip install --python venvTrading/bin/python pyclustering mplfinance PyYAML pandas
/home/kiluh/.local/bin/uv pip install --python venvTrading/bin/python -e .  # once setup.cfg/pyproject defined
```
*(Do not invoke system `pip`; always pass `--python venvTrading/bin/python`.)*

Activate the environment when running scripts interactively:
```bash
source venvTrading/bin/activate
```

## Backtest & Validation Workflows

### Run In-Sample Excellence Test
```bash
python -m src.strategies.flag_patterns.tests.runInSampleExcellence \
  --seed 42 \
  --data-source csv:/data/BTCUSDT3600.csv \
  --artifacts-dir artifacts/flag_patterns/excellence-seed-42
```
- Generates CSV/JSON summary and PNG plots under the specified artifacts directory.
- Uses vendored TechnicalAnalysisAutomation modules through the strategy wrapper.

### In-Sample Permutation Significance Test
```bash
python -m src.strategies.flag_patterns.tests.runInSamplePermutation \
  --seed 42 \
  --permutations 1000 \
  --data-source csv:/data/BTCUSDT3600.csv \
  --artifacts-dir artifacts/flag_patterns/permute-seed-42
```
- Leverages `mcpt.bar_permute.get_permutation` to quantify random-chance performance.

### Walk-Forward Validation
```bash
python -m src.strategies.flag_patterns.tests.runWalkForward \
  --seed 42 \
  --window 180d \
  --step 30d \
  --data-source exchange:binance:BTC/USDT:1h \
  --artifacts-dir artifacts/flag_patterns/wf-seed-42
```
- Pulls data via `DataSourceBase`, slices rolling windows, and emits performance metrics per fold.

### Walk-Forward Permutation
```bash
python -m src.strategies.flag_patterns.tests.runWalkForwardPermutation \
  --seed 42 \
  --window 180d \
  --step 30d \
  --permutations 250 \
  --data-source exchange:binance:BTC/USDT:1h \
  --artifacts-dir artifacts/flag_patterns/wf-permute-seed-42
```
- Produces permutation-adjusted walk-forward statistics and aggregated artifact bundle.

## Live / Paper Trading
1. Ensure validation runners pass CI gates and artifacts reviewed.
2. Configure strategy parameters in `src/strategies/flag_patterns/params.yaml` (per-trade risk %, hold multiplier).
3. Populate credentials in `.env` (Telegram bot token, exchange keys).
4. Launch paper session:
   ```bash
   python -m geb live \
     --strategy flag_patterns \
     --exchange binance \
     --symbol BTC/USDT \
     --timeframe 1h \
     --seed 42
   ```
5. Monitor via Telegram commands (`/status`, `/positions`, `/close_all`) and CLI dashboard.

## Artifact Review
- All runs should produce metric summaries under `artifacts/flag_patterns/` with structured JSON + charts.
- Upload artifacts as part of PR checklist; ensure CI references them in summary output.

## Troubleshooting
- If numpy incompatibility appears, pin version via `uv pip install --python venvTrading/bin/python "numpy==1.23.1"` and rerun tests.
- Verify vendored TechnicalAnalysisAutomation modules remain in sync with upstream commit noted in `src/strategies/flag_patterns/README.md`.
- Use `python -m pip` *only* within the activated `venvTrading` if `uv` is unavailable (last resort).
