# Executed workflow report

Data: **synthetic**. This is a controlled workflow demonstration, not market alpha or a reproduction of employer results.

The input has 15,120 observations, 20 assets and 756 supplied sessions. The six default proposals are fixtures, not outputs of a live language model. External proposal lists use the same validator.

## Technical admission and research selection

candidate,status,reason,expression_sha256
momentum20,ADMITTED,Technical contract passed; no alpha claim,ed0751f516c8f920aa3faa889888737d7e09563309a399d866a85d7ad8c174c7
reversal5,ADMITTED,Technical contract passed; no alpha claim,140d77265a55b7432688c4bc82ec8931937479cedcfa93517eb5b7fad1f4162c
volatility20,ADMITTED,Technical contract passed; no alpha claim,a4879a978f91b6fd415f63ef61284e6b5eec52978ecf097843cc27f0f77f136d
duplicate_momentum,DUPLICATE,Same canonical expression as momentum20,ed0751f516c8f920aa3faa889888737d7e09563309a399d866a85d7ad8c174c7
future_reference,REJECTED,Window must be an integer between 1 and 60; future references forbidden,
unsupported_depth,REJECTED,Unsupported field,


Technical validity does not demonstrate predictive value. Three usable factors are compared only in development. Their orientation is chosen on training dates, and the winner is selected on validation. The frozen choice is **momentum20**.

## Confirmation

Mean daily RankIC: **-0.070697**. Moving-block date-bootstrap 95% interval: **[-0.121853, -0.030381]**, 1,000 resamples of ten-date blocks.

![Development and confirmation](validation.png)

Split dates/rows, fitted moments and the selection rule are recorded in freeze.json. Cross-boundary five-session labels are removed using their end dates. The interval describes the frozen run; it does not cover every research decision or arbitrary long-memory dependence. IC is not trading P&L.

## Recovery and limits

Run with --stop-after frozen, then --resume to demonstrate stage recovery. Identical completed resumes return saved metrics. Changed inputs, source, tracked artifacts or broken lineage are rejected. Fingerprints detect accidental inconsistencies, not a malicious actor who can rewrite every local file. A crash during an unsealed stage requires a fresh output directory; only sealed stages are restartable.

No model, paid API, Qlib runtime, broker, company dataset or secret is used. Synthetic relationships and the chosen small search space limit every economic conclusion. See METHODS and WALKTHROUGH for the complete interpretation.
