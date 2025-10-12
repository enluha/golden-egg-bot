# Phase 0 Research – Flag Patterns Strategy Integration

**Date:** 2025-10-12  
**Branch:** `001-integrate-flag-patterns`

## Research Goals
- Confirm licensing and reuse constraints for upstream repos.
- Identify callable entry points and dependencies for TechnicalAnalysisAutomation (TAA) flag strategy code.
- Document mcpt permutation & walk-forward APIs needed for validation runners.
- Surface integration risks (runtime deps, data formats, packaging gaps) before design tasks.

## Findings

### 1. TechnicalAnalysisAutomation (https://github.com/neurotrader888/TechnicalAnalysisAutomation)
- **License:** MIT (per `LICENSE`, commit `3466e82`). Compatible with GoldenEggBot requirements; attribution required when vendoring.
- **Key Modules & Functions:**
  - `flags_pennants.py` exposing `find_flags_pennants_pips(data: np.ndarray, order: int)` and `find_flags_pennants_trendline(...)`. Returns lists of `FlagPattern` dataclasses describing entries/exits, slopes, confirmation index.
  - `trendline_automation.py` with `fit_trendlines_single` used under the hood for resistance/support calculations.
  - `perceptually_important.py` (`find_pips`) and `rolling_window.py` (`rw_top`, `rw_bottom`) used to derive flag boundaries.
  - `test_flag_patterns.py` demonstrates usage with `BTCUSDT3600.csv`, calculates returns, and plots results—useful blueprint for our `*_is_excellence.py` runner.
- **Dependencies:** expects `numpy==1.23.1` (README note to satisfy `pyclustering`), plus `pandas`, `mplfinance`, `matplotlib`. Need to confirm compatibility with GoldenEggBot’s Python 3.11 stack; may require pin override or substituting `pyclustering` usage if it breaks.
- **Data Expectations:** scripts load CSVs with columns `date`, `open`, `high`, `low`, `close` (log-transformed). We must adapt to GoldenEggBot data pipeline (DataSourceBase) and convert to expected numpy arrays.
- **Packaging:** repo is flat (no package structure). Recommended integration options:
  1. Vendor selected modules into `src/strategies/flag_patterns/upstream/` with attribution.
  2. Add git submodule and import via `sys.path` adjustments or local package install.
  3. Build lightweight wrapper wheel (out of scopefor now). Vendoring minimal required modules (flags, trendline, perceptually_important, rolling_window) keeps dependencies manageable.

### 2. mcpt permutation & walk-forward tooling (https://github.com/neurotrader888/mcpt)
- **License:** MIT (per `LICENSE`, commit `501c306`). Compatible with redistribution.
- **Relevant Entry Points:**
  - `bar_permute.get_permutation(ohlc, start_index=0, seed=None)` generates permuted series preserving intrabar structure; suits our `*_is_permute.py` runner.
  - `donchian.walkforward_donch(...)` + `walkforward_donchian_mcpt.py` show how to orchestrate walk-forward backtests; analogous patterns can be reused for Flag Patterns by substituting strategy callback.
  - Additional helper scripts (`insample_donchian_mcpt.py`, `insample_tree_mcpt.py`) illustrate how permutation and walk-forward outputs are summarized (useful for our artifact schema).
- **Dependencies:** relies on `pandas`, `numpy`, `matplotlib`, `tqdm`. No compiled extensions.
- **Packaging:** also flat structure; vendor or submodule approach similar to TAA. Plan to wrap functions inside GoldenEggBot validation scripts rather than modifying upstream code.

### 3. Integration Considerations & Risks
- **Version Alignment:** TAA recommends `numpy==1.23.1` for `pyclustering`. Need to test against our baseline (likely newer). If incompatibility occurs, options include pinning numpy for strategy runners, swapping out `pyclustering`, or adjusting code to avoid it.
- **Data Interfaces:** Both repos expect local CSV/Parquet files. GoldenEggBot should provide adapters that fetch klines via `DataSourceBase`, convert to DataFrame/ndarray, and pass to upstream functions. Ensure timezone alignment and log transformations replicate original scripts.
- **Visualization:** Upstream plotting uses `matplotlib`/`mplfinance`. For telemetry snapshots we must generate plots headlessly and export to PNG (likely via Agg backend) before uploading to Telegram.
- **Testing Harness:** Upstream scripts are procedural. We must encapsulate them into callable functions (e.g., `run_excellence_test(seed, data_path)`) so CI can execute headless runs without interactive plotting. Save summary metrics + charts to `artifacts/flag_patterns/` with deterministic filenames.
- **Licensing Compliance:** MIT requires inclusion of copyright notice. Add attribution headers in vendored files and note upstream repos in strategy README.
- **Submodule vs Vendoring Decision:** Submodules allow tracking upstream updates but complicate packaging; vendoring ensures reproducibility. Recommendation: vendor minimal subset with clear `UPSTREAM_VERSION` metadata and add follow-up task to automate updates.

## Outstanding Questions / TODOs
- Confirm whether `pyclustering` is strictly required by the portions we need; if yes, assess compatibility with Python 3.11/uv environment.
- Determine canonical dataset sources for validation (e.g., GoldenEggBot sample CSV vs upstream `BTCUSDT3600.csv`). Need reproducible, licensed sample data for artifacts.
- Decide on artifact metric schema (e.g., JSON summary fields for counts, win rate, expectancy) to integrate with CI reporting.

## Next Steps
1. Validate numpy/pyclustering compatibility inside GoldenEggBot uv env; document required version pins or fallbacks.
2. Prototype minimal wrapper that loads historical klines through DataSourceBase and feeds them to `find_flags_pennants_pips`. Measure performance and confirm outputs align with upstream script.
3. Draft design for deterministic validation runners using mcpt functions (define CLI params, artifact filenames, summary metrics).
4. Update plan milestones with any mitigation tasks once compatibility tests complete.

### 4. Compatibility Smoke Test (uv + venvTrading)
- Used existing virtual environment `venvTrading` (Python 3.12.3) with `uv` installer located at `/home/kiluh/.local/bin/uv`.
- Installed `pyclustering==0.10.1.2` plus dependencies (`numpy 2.3.3`, `scipy 1.16.2`, `matplotlib 3.10.7`, `kiwisolver 1.4.9`, `packaging 25.0`) via `uv pip install --python venvTrading/bin/python`.
- `venvTrading/bin/python -c "import pyclustering"` succeeds, confirming compatibility with Python 3.12 despite upstream README recommending `numpy==1.23.1`.
- Action item: run Flag Patterns integration tests after wiring strategy to ensure numerical results match expectations under the newer numpy version; be prepared to pin numpy if discrepancies arise.
