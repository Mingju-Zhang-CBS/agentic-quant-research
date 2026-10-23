# Walkthrough: from a candidate to a decision

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
