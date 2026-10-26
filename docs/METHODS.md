# Methods and input contracts

## What the workflow is

An offline controller makes the research sequence inspectable. The proposer is a fixed JSON fixture by default. A human or an external language model may supply a different JSON list through the same contract. No language model is called, and this repository does not implement the full RD-Agent or Qlib system. It is an independently written companion illustrating public research principles.

## Market and proposal contracts

CSV columns must be exactly `date,asset,open,high,low,close,volume`. Keys are unique, dates are timezone-naive session dates and every asset appears on every supplied date. Prices are finite and positive, volume is finite and nonnegative, and OHLC bounds must agree. At least three assets and 100 supplied sessions are required. There is no implicit missing-price fill or calendar inference.

Each proposal has exactly `id`, `hypothesis` and `expression`. IDs are unique nonempty strings and hypotheses are nonempty text. Expressions are JSON trees, at most eight nested edges deep. Operators are `return(field,window)`, `lag(field,window)`, `negate(input)` and `rolling_std(input,window)`. Fields are the five supplied OHLCV fields; windows are integer 1–60, excluding booleans. Rolling standard deviation uses `ddof=1` and a full window. Arbitrary code, unknown keys, unavailable fields and negative lags are rejected.

Canonical sorted JSON defines identity. Identical trees under different IDs are duplicates. This is syntactic canonicalization, not a proof that all algebraically equivalent expressions are detected. Admission only establishes the technical contract.

## Synthetic market and timing

The default generator has 20 assets and 756 business-date labels starting in 2020. They are generated dates, not an exchange calendar. Returns combine a common Gaussian shock, idiosyncratic Gaussian shocks, a small drift and 0.06 times the previous generated return. OHLC ranges and volumes are synthetic. This mechanism and the fixed seed are design assumptions, not empirical market findings.

The research target is `close[t+5]/close[t]-1`. A factor at session t uses observations through that close. This is a predictive-correlation study with no same-close fill assumption, financing or executable strategy.

## Partition and fitted transformations

Dates with any missing factor history or unavailable five-session target are removed from the shared research sample. The first 60% of complete dates define the training region, the next 20% validation and the remainder confirmation; integer cut points use floor. Training labels whose end reaches validation are excluded. Validation labels whose end reaches confirmation are excluded. All assets on a date remain together.

For each admitted factor, mean and population standard deviation are fitted only on retained training rows. The factor's direction is the sign of its training mean daily RankIC, with zero choosing +1. Validation compares these fixed directions. The highest validation mean daily RankIC wins; candidate ID resolves ties. There is no refit using validation moments or confirmation labels.

The full admitted cohort, fitted moments, orientation, partition and winner are frozen before confirmation. Cross-sectional RankIC is Pearson correlation between average-rank scores and average-rank five-session returns, computed per date. Constant cross sections are excluded and at least ten usable dates are required.

## Uncertainty and recorded outcome

Confirmation reports the mean daily RankIC and a 1,000-resample moving-block bootstrap with ten consecutive dates per block, sampled with replacement and truncated to the original date count. Blocks preserve some local dependence from overlapping targets; they do not model arbitrary dependence or the entire prior search. Results are conditional on this synthetic generator and frozen process. The default selected factor has a negative confirmation IC; the research failure is retained.

## Artifacts, recovery and integrity

`manifest.json` binds normalized input bytes, proposal content, package source, configuration and dependency versions. `admission.csv`, `development.csv`, `freeze.json` and `confirmation_daily.csv` separate stages. `lineage.jsonl` records sequenced, hash-linked sealed-stage events; `checkpoint.json` records artifact digests and input identity.

Existing outputs require `--resume`. Changed data, proposals, configuration, source, tracked artifacts or lineage fail closed. A completed resume returns saved metrics without appending another event. Recovery is supported at sealed admitted/frozen/complete stages. A crash inside an unsealed stage can leave files that require a fresh output directory. There is one writer per run; no concurrent-writer or hostile-filesystem guarantee is made. Hashes are consistency checks, not cryptographic provenance from an independent party.

Elapsed time is one local workload through statistics, before plotting; it is not an LLM benchmark or production throughput. See the manifest for the actual Python/dependency environment.

Reference: [Microsoft RD-Agent](https://github.com/microsoft/RD-Agent). Its public framework and authors retain attribution. None of its original benchmark results, company integrations or factor libraries are claimed here.


## Worked example and interpretation


## 1. Inspect a proposal

```json
{"id":"momentum20","hypothesis":"Medium-horizon continuation is a testable hypothesis.","expression":{"op":"return","field":"close","window":20}}
```

If the current close is 105 and the close twenty sessions earlier is 100, the raw factor is `105/100-1 = 0.05`. The feature can be computed after the current close. The future five-session return is a separate label and cannot be read by the expression evaluator.

A proposal named `another_momentum` with the same expression is a duplicate. A lag of -1 would read a future observation and is rejected. `bid_depth` is also rejected because daily OHLCV does not provide it. These outcomes remain in admission.csv rather than vanishing from the narrative.

## 2. Follow the dates

The input has 756 supplied sessions. The longest default history removes the first twenty dates; five-session targets remove the final five. This leaves 731 complete dates. Floor cut points create 438 training-region dates, 146 validation-region dates and 147 confirmation dates. Five boundary dates are removed from each of the first two regions. The retained counts are **433 / 141 / 147**, with twenty asset rows per date.

This is label-end purging. A row before a boundary can still be excluded when its target finishes on the other side. Feature histories may use earlier observations across a boundary; future outcomes may not.

## 3. Fit and select once

For each factor, calculate training-only mean and scale. With illustrative values mean=0.01 and scale=0.02, a raw value 0.05 becomes `(0.05-0.01)/0.02 = 2`. The actual values are in freeze.json. The sign choice uses training IC. Validation selects the fixed candidate; confirmation does not change the sign, moments or winner.

The actual default winner is **momentum20**. Its validation mean RankIC is positive, but the later confirmation mean is **-0.0707**, with a ten-date block interval **[-0.1219, -0.0304]**. This is an unsuccessful synthetic forecasting result. The workflow's contribution is that it makes the failure visible and reproducible.

## 4. Exercise recovery

```text
python -m agentic_quant_research --demo --output local-runs/recovery --stop-after frozen
python -m agentic_quant_research --demo --output local-runs/recovery --resume
python -m agentic_quant_research --demo --output local-runs/recovery --resume
```

The first command seals development without producing confirmation metrics. The second verifies the checkpoint, continues confirmation and seals the report. The third returns saved results. Tests additionally alter an artifact, alter a proposal and alter a lineage event: each is rejected. An unsealed mid-stage crash is intentionally not silently repaired.

## 5. Read the implementation

`validate_market` establishes the panel contract; `admit` and `validate_expression` establish technical eligibility. `calculate_factor` reads past/current market observations. `date_split` constructs labels and purged partitions. `daily_ic` and `bootstrap_interval` calculate the research statistics. `run_workflow` sequences the stages and writes immutable artifacts.

Run `python examples/explain_workflow.py` for an executable small-panel example. A valid factor expression, a selected candidate and a positive development metric are three different facts. None is a statement that the factor works in markets.
