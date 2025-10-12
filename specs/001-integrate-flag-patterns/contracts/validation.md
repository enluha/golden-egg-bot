# Contract – Flag Patterns Validation Runners

Defines command-line interfaces and outputs for the four mandatory validation scripts.

## Shared CLI Arguments
- `--seed <int>`: RNG seed (required). Ensures deterministic permutations and walk-forward splits.
- `--data-source <str>`: Data locator string (`csv:/path`, `exchange:<id>:<symbol>:<tf>`).
- `--artifacts-dir <path>`: Target directory for metrics and plots (must be created if absent).
- `--config <path>` (optional): Alternate strategy parameter YAML; defaults to `params.yaml`.

## Scripts

### `flag_patterns_is_excellence.py`
- Purpose: Baseline performance on holdout dataset using configured parameters.
- Outputs:
  - `metrics.json`: expectation, win rate, average return by pattern type.
  - `patterns.csv`: row per detected pattern with metadata.
  - `chart_*.png`: visuals for sample trades.

### `flag_patterns_is_permute.py`
- Additional Args: `--permutations <int>` (default 1000).
- Uses `mcpt.bar_permute.get_permutation` to produce randomized datasets.
- Outputs:
  - `permutation_stats.json`: p-value, z-score, distribution summary.
  - `hist_permutation.png`: histogram of randomized performance.

### `flag_patterns_wf_test.py`
- Additional Args: `--window <duration>`, `--step <duration>`.
- Performs rolling walk-forward evaluation with real data.
- Outputs `wf_metrics.json` (per window results) and aggregated charts.

### `flag_patterns_wf_permute.py`
- Combines walk-forward slicing with permutation significance testing.
- Additional Args: inherits from wf + permute; may support `--permutations-per-window`.
- Outputs aggregated metrics plus per-window permutation stats.

## Artifact Naming Convention
```
artifacts/flag_patterns/<script>/seed-<seed>/run-<timestamp>/...
```
- Each run adds `run.json` manifest containing config hash, dataset hash, and upstream commit references.

## Exit Codes
- `0`: success, all thresholds satisfied.
- `2`: statistical threshold not met (e.g., p-value > limit); pipeline should block promotion.
- `3`: data issues (missing candles, NaNs).
- Non-zero codes must print actionable error message to stderr.

