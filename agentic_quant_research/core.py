"""Small auditable research workflow, independently implemented from public methods."""
from __future__ import annotations

import hashlib
import importlib.metadata
import io
import json
import platform
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

FIELDS = {"open", "high", "low", "close", "volume"}
SEED = 20261023


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def digest(data):
    return hashlib.sha256(data).hexdigest()


def source_hashes():
    return {p.name: digest(p.read_bytes()) for p in sorted(Path(__file__).parent.glob("*.py"))}


def generate_market(assets=20, sessions=756, seed=SEED):
    if not isinstance(assets, int) or assets < 3 or not isinstance(sessions, int) or sessions < 100:
        raise ValueError("Use at least three assets and 100 sessions")
    rng = np.random.default_rng(seed)
    common = rng.normal(0, .006, (sessions, 1))
    returns = .00015 + common + rng.normal(0, .012, (sessions, assets))
    # Weak short-lived structure is a generating assumption, not discovered market alpha.
    for i in range(1, sessions):
        returns[i] += .06 * returns[i - 1]
    close = 100 * np.exp(np.cumsum(returns, axis=0))
    opening = close * np.exp(rng.normal(0, .003, close.shape))
    spread = np.abs(rng.normal(.004, .002, close.shape))
    return pd.DataFrame({
        "date": np.repeat(pd.bdate_range("2020-01-02", periods=sessions), assets),
        "asset": np.tile([f"A{i:02d}" for i in range(assets)], sessions),
        "open": opening.ravel(), "high": (np.maximum(opening, close) * (1 + spread)).ravel(),
        "low": (np.minimum(opening, close) / (1 + spread)).ravel(), "close": close.ravel(),
        "volume": rng.integers(10000, 1000000, close.shape).ravel(),
    })


def validate_market(frame):
    required = {"date", "asset"} | FIELDS
    if set(frame.columns) != required or frame.empty:
        raise ValueError("Market must contain exactly date,asset,open,high,low,close,volume")
    data = frame.copy()
    data[sorted(FIELDS)] = data[sorted(FIELDS)].apply(pd.to_numeric, errors="raise")
    data["date"] = pd.to_datetime(data["date"], errors="raise")
    if data.date.dt.tz is not None or not data.date.eq(data.date.dt.normalize()).all():
        raise ValueError("Dates must be timezone-naive session dates")
    if data.asset.isna().any() or not data.asset.map(lambda x: isinstance(x, str) and bool(x.strip())).all():
        raise ValueError("Asset identifiers must be nonempty strings")
    if data.duplicated(["date", "asset"]).any() or data.date.isna().any():
        raise ValueError("Unique nonmissing date/asset keys required")
    values = data[sorted(FIELDS)].to_numpy(dtype=float)
    if not np.isfinite(values).all() or (data[list(FIELDS - {"volume"})] <= 0).any().any() or (data.volume < 0).any():
        raise ValueError("Finite prices > 0 and volume >= 0 required")
    if (data.high < data[["open", "close", "low"]].max(axis=1)).any() or (data.low > data[["open", "close", "high"]].min(axis=1)).any():
        raise ValueError("OHLC bounds inconsistent")
    counts = data.groupby("date").asset.nunique()
    if data.asset.nunique() < 3 or not counts.eq(data.asset.nunique()).all() or len(counts) < 100:
        raise ValueError("Balanced panel with >=3 assets and >=100 sessions required")
    return data.sort_values(["date", "asset"]).reset_index(drop=True)


def default_proposals():
    momentum = {"op": "return", "field": "close", "window": 20}
    return [
        {"id": "momentum20", "hypothesis": "Medium-horizon continuation is a testable hypothesis.", "expression": momentum},
        {"id": "reversal5", "hypothesis": "Recent price movements may reverse.", "expression": {"op": "negate", "input": {"op": "return", "field": "close", "window": 5}}},
        {"id": "volatility20", "hypothesis": "Realized risk may help describe subsequent cross-sectional returns.", "expression": {"op": "rolling_std", "window": 20, "input": {"op": "return", "field": "close", "window": 1}}},
        {"id": "duplicate_momentum", "hypothesis": "A second name must not create a second independent idea.", "expression": dict(momentum)},
        {"id": "future_reference", "hypothesis": "Deliberately invalid future reference.", "expression": {"op": "lag", "field": "close", "window": -1}},
        {"id": "unsupported_depth", "hypothesis": "Deliberately unavailable order-book field.", "expression": {"op": "lag", "field": "bid_depth", "window": 1}},
    ]


def validate_expression(expr, depth=0):
    if not isinstance(expr, dict) or depth > 8:
        raise ValueError("Expression must be a bounded JSON object")
    op = expr.get("op")
    expected = {"return": {"op", "field", "window"}, "lag": {"op", "field", "window"},
                "rolling_std": {"op", "window", "input"}, "negate": {"op", "input"}}
    if op not in expected or set(expr) != expected[op]:
        raise ValueError("Unsupported operator or expression keys")
    if "field" in expr and expr["field"] not in FIELDS:
        raise ValueError("Unsupported field")
    if "window" in expr:
        n = expr["window"]
        if isinstance(n, bool) or not isinstance(n, int) or not 1 <= n <= 60:
            raise ValueError("Window must be an integer between 1 and 60; future references forbidden")
    if "input" in expr:
        validate_expression(expr["input"], depth + 1)
    return canonical(expr)


def admit(proposals):
    if not isinstance(proposals, list) or not 1 <= len(proposals) <= 100:
        raise ValueError("One to 100 proposal objects required")
    identifiers = [p.get("id") for p in proposals if isinstance(p, dict)]
    if len(identifiers) != len(proposals) or any(not isinstance(x, str) or not x.strip() for x in identifiers) or len(set(identifiers)) != len(identifiers):
        raise ValueError("Unique nonempty proposal IDs required")
    seen, rows, accepted = {}, [], []
    for proposal in proposals:
        try:
            if set(proposal) != {"id", "hypothesis", "expression"} or not isinstance(proposal["hypothesis"], str) or not proposal["hypothesis"].strip():
                raise ValueError("Each proposal needs id, nonempty hypothesis and expression")
            expression = validate_expression(proposal["expression"])
            identity = digest(expression.encode())
            if identity in seen:
                status, reason = "DUPLICATE", "Same canonical expression as " + seen[identity]
            else:
                seen[identity] = proposal["id"]
                accepted.append(proposal)
                status, reason = "ADMITTED", "Technical contract passed; no alpha claim"
        except (ValueError, TypeError) as error:
            identity, status, reason = "", "REJECTED", str(error)
        rows.append({"candidate": proposal["id"], "status": status, "reason": reason, "expression_sha256": identity})
    if not accepted:
        raise ValueError("No technically admissible candidates")
    return pd.DataFrame(rows), accepted


def calculate_factor(data, expr):
    validate_expression(expr)
    op = expr["op"]
    if op in {"return", "lag"}:
        grouped = data.groupby("asset", sort=False)[expr["field"]]
        return grouped.pct_change(expr["window"], fill_method=None) if op == "return" else grouped.shift(expr["window"])
    child = calculate_factor(data, expr["input"])
    if op == "negate":
        return -child
    return child.groupby(data.asset, sort=False).transform(lambda series: series.rolling(expr["window"], min_periods=expr["window"]).std(ddof=1))


def date_split(data, factors, horizon=5):
    if isinstance(horizon, bool) or not isinstance(horizon, int) or horizon < 1:
        raise ValueError("Positive integer horizon required")
    dates = data.date.drop_duplicates().to_numpy()
    ranks = pd.Series(np.arange(len(dates)), index=dates)
    position = data.date.map(ranks).to_numpy(dtype=int)
    labels = data.groupby("asset", sort=False).close.shift(-horizon) / data.close - 1
    finite = np.isfinite(labels.to_numpy()) & np.isfinite(factors.to_numpy()).all(axis=1)
    eligible = data.loc[finite, "date"].drop_duplicates().to_numpy()
    if len(eligible) < 60:
        raise ValueError("Not enough complete dates after feature histories and labels")
    first_validation = eligible[int(len(eligible) * .6)]
    first_confirmation = eligible[int(len(eligible) * .8)]
    validation_index, confirmation_index = int(ranks[first_validation]), int(ranks[first_confirmation])
    masks = {
        "train": finite & (position < validation_index) & (position + horizon < validation_index),
        "validation": finite & (position >= validation_index) & (position < confirmation_index) & (position + horizon < confirmation_index),
        "confirmation": finite & (position >= confirmation_index),
    }
    if any(data.loc[mask, "date"].nunique() < 10 for mask in masks.values()):
        raise ValueError("At least ten complete dates per partition required")
    return labels, masks, {"horizon_sessions": horizon, "first_validation": str(pd.Timestamp(first_validation).date()),
                           "first_confirmation": str(pd.Timestamp(first_confirmation).date()),
                           "dates": {k: int(data.loc[v, "date"].nunique()) for k, v in masks.items()},
                           "rows": {k: int(v.sum()) for k, v in masks.items()},
                           "purged_boundary_dates": int(len(eligible) - sum(data.loc[v, "date"].nunique() for v in masks.values()))}


def daily_ic(data, score, labels, mask):
    sample = pd.DataFrame({"date": data.date[mask], "score": score[mask], "label": labels[mask]})
    rows = []
    for date, group in sample.groupby("date", sort=True):
        x, y = group.score.rank().to_numpy(), group.label.rank().to_numpy()
        if np.std(x) > 0 and np.std(y) > 0:
            rows.append({"date": str(date.date()), "rank_ic": float(np.corrcoef(x, y)[0, 1])})
    if len(rows) < 10:
        raise ValueError("At least ten nonconstant daily cross sections required")
    return pd.DataFrame(rows)


def bootstrap_interval(values, seed=SEED, resamples=1000, block=10):
    values = np.asarray(values, dtype=float)
    if values.ndim != 1 or len(values) < block or not np.isfinite(values).all():
        raise ValueError("Finite daily IC vector long enough for blocks required")
    rng = np.random.default_rng(seed)
    starts = rng.integers(0, len(values) - block + 1, (resamples, int(np.ceil(len(values) / block))))
    indexes = (starts[..., None] + np.arange(block)).reshape(resamples, -1)[:, :len(values)]
    return np.quantile(values[indexes].mean(axis=1), [.025, .975]).tolist()


def _json_bytes(value):
    return (json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n").encode()


def _immutable(path, content):
    if path.exists():
        if path.read_bytes() != content:
            raise ValueError("Existing artifact differs: " + path.name)
        return
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_bytes(content)
    temporary.replace(path)


def verify_lineage(path):
    previous = "0" * 64
    for number, line in enumerate(path.read_text().splitlines(), 1):
        record = json.loads(line)
        claimed = record.pop("hash")
        if record["sequence"] != number or record["previous"] != previous or digest(canonical(record).encode()) != claimed:
            raise ValueError("Lineage chain integrity failed")
        previous = claimed
    return previous


def run_workflow(market, proposals, output, *, resume=False, stop_after=None, data_kind="user-supplied"):
    started = time.perf_counter()
    if data_kind not in {"synthetic", "user-supplied"} or stop_after not in {None, "admitted", "frozen"}:
        raise ValueError("Invalid run mode")
    data = validate_market(market)
    admission, accepted = admit(proposals)
    configuration = {"horizon_sessions": 5, "partition": [.6, .2, .2], "bootstrap_resamples": 1000, "bootstrap_block_dates": 10, "seed": SEED}
    identity = {"data_kind": data_kind, "input_sha256": digest(data.to_csv(index=False, lineterminator="\n").encode()),
                "proposals_sha256": digest(canonical(proposals).encode()), "configuration": configuration, "source_sha256": source_hashes()}
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    checkpoint_path = output / "checkpoint.json"
    if checkpoint_path.exists():
        if not resume:
            raise ValueError("Output already exists; use resume with identical inputs")
        checkpoint = json.loads(checkpoint_path.read_text())
        if checkpoint["identity"] != identity:
            raise ValueError("Resume input/configuration/source identity differs")
        for name, sha in checkpoint["artifacts"].items():
            if Path(name).name != name or not (output / name).is_file() or digest((output / name).read_bytes()) != sha:
                raise ValueError("Artifact integrity failed")
        verify_lineage(output / "lineage.jsonl")
        if digest((output / "lineage.jsonl").read_bytes()) != checkpoint["lineage_sha256"]:
            raise ValueError("Lineage checkpoint fingerprint differs")
        if checkpoint["stage"] == "complete":
            return json.loads((output / "metrics.json").read_text())
    else:
        if any(output.iterdir()):
            raise ValueError("Output must be empty or have a verified checkpoint")
        checkpoint = {"identity": identity, "stage": "new", "artifacts": {}}

    def put(name, content):
        _immutable(output / name, content)
        checkpoint["artifacts"][name] = digest(content)

    def seal(stage):
        lineage = output / "lineage.jsonl"
        previous = verify_lineage(lineage) if lineage.exists() else "0" * 64
        sequence = len(lineage.read_text().splitlines()) + 1 if lineage.exists() else 1
        record = {"sequence": sequence, "previous": previous, "stage": stage, "artifacts": dict(checkpoint["artifacts"])}
        record["hash"] = digest(canonical(record).encode())
        with lineage.open("a", encoding="utf-8", newline="\n") as handle:
            handle.write(canonical(record) + "\n")
        checkpoint["stage"] = stage
        checkpoint["lineage_sha256"] = digest(lineage.read_bytes())
        temporary = checkpoint_path.with_suffix(".tmp")
        temporary.write_bytes(_json_bytes(checkpoint))
        temporary.replace(checkpoint_path)

    if checkpoint["stage"] == "new":
        manifest = dict(identity, schema_version="research-studio-run-v1", created_utc=datetime.now(timezone.utc).isoformat(),
                        environment={"python": platform.python_version(), "platform": platform.system(),
                                     "dependencies": {n: importlib.metadata.version(n) for n in ["numpy", "pandas", "matplotlib"]}})
        put("manifest.json", _json_bytes(manifest))
        put("admission.csv", admission.to_csv(index=False, lineterminator="\n").encode())
        seal("admitted")
    if stop_after == "admitted":
        return {"stage": "admitted"}

    factors = pd.DataFrame({p["id"]: calculate_factor(data, p["expression"]) for p in accepted})
    labels, masks, split = date_split(data, factors)
    preprocessing, development = {}, []
    for name in factors:
        training = factors.loc[masks["train"], name]
        mean, scale = float(training.mean()), float(training.std(ddof=0))
        if not np.isfinite(scale) or scale <= 0:
            raise ValueError("Training factor variance must be positive")
        standardized = (factors[name] - mean) / scale
        train_ic = daily_ic(data, standardized, labels, masks["train"]).rank_ic.mean()
        orientation = 1 if train_ic >= 0 else -1
        valid_ic = daily_ic(data, orientation * standardized, labels, masks["validation"]).rank_ic.mean()
        preprocessing[name] = {"mean": mean, "scale": scale, "orientation": orientation, "fitted_partition": "train"}
        development.append({"candidate": name, "train_rank_ic_raw": float(train_ic), "orientation_from_train": orientation, "validation_rank_ic": float(valid_ic)})
    development = pd.DataFrame(development).sort_values(["validation_rank_ic", "candidate"], ascending=[False, True]).reset_index(drop=True)
    selected = development.iloc[0].candidate
    freeze = {"eligible_candidates": sorted(factors.columns), "selected": selected, "rule": "highest validation mean RankIC after training-only sign choice; candidate ID breaks ties", "preprocessing": preprocessing, "split": split}
    if checkpoint["stage"] == "admitted":
        put("development.csv", development.to_csv(index=False, lineterminator="\n").encode())
        put("freeze.json", _json_bytes(freeze))
        seal("frozen")
    else:
        if json.loads((output / "freeze.json").read_text()) != freeze:
            raise ValueError("Recomputed development differs from frozen cohort")
    if stop_after == "frozen":
        return {"stage": "frozen", "selected": selected}

    fitted = preprocessing[selected]
    score = fitted["orientation"] * (factors[selected] - fitted["mean"]) / fitted["scale"]
    daily = daily_ic(data, score, labels, masks["confirmation"])
    metrics = {"data_kind": data_kind, "selected": selected, "candidate_status": admission.status.value_counts().to_dict(),
               "split": split, "confirmation_mean_rank_ic": float(daily.rank_ic.mean()),
               "confirmation_95_interval": bootstrap_interval(daily.rank_ic), "configuration": configuration,
               "elapsed_seconds": float(time.perf_counter() - started), "model_calls": 0, "paid_api_calls": 0,
               "measurement": {"workload": "one local complete workflow; elapsed time includes validation, factors and research statistics, before plotting", "python": platform.python_version(), "platform": platform.system()}}
    put("confirmation_daily.csv", daily.to_csv(index=False, lineterminator="\n").encode())
    put("metrics.json", _json_bytes(metrics))
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig, axes = plt.subplots(1, 2, figsize=(11, 3.8))
    axes[0].bar(development.candidate, development.validation_rank_ic, color="#36B3A8")
    axes[0].axhline(0, color="#59636e", linewidth=.8)
    axes[0].set(title="Development comparison", ylabel="Validation mean RankIC")
    axes[1].plot(pd.to_datetime(daily.date), daily.rank_ic.rolling(20, min_periods=20).mean(), color="#234e70")
    axes[1].axhline(0, color="#59636e", linewidth=.8)
    axes[1].set(title="Frozen selection: confirmation", ylabel="20-date rolling RankIC")
    fig.autofmt_xdate(); fig.tight_layout()
    buffer = io.BytesIO(); fig.savefig(buffer, format="png", dpi=140); plt.close(fig)
    put("validation.png", buffer.getvalue())
    interval = metrics["confirmation_95_interval"]
    report = f"""# Executed workflow report

Data: **{data_kind}**. This is a controlled workflow demonstration, not market alpha or a reproduction of employer results.

The input has {len(data):,} observations, {data.asset.nunique()} assets and {data.date.nunique()} supplied sessions. The six default proposals are fixtures, not outputs of a live language model. External proposal lists use the same validator.

## Technical admission and research selection

{admission.to_csv(index=False)}

Technical validity does not demonstrate predictive value. Three usable factors are compared only in development. Their orientation is chosen on training dates, and the winner is selected on validation. The frozen choice is **{selected}**.

## Confirmation

Mean daily RankIC: **{metrics['confirmation_mean_rank_ic']:.6f}**. Moving-block date-bootstrap 95% interval: **[{interval[0]:.6f}, {interval[1]:.6f}]**, 1,000 resamples of ten-date blocks.

![Development and confirmation](validation.png)

Split dates/rows, fitted moments and the selection rule are recorded in freeze.json. Cross-boundary five-session labels are removed using their end dates. The interval describes the frozen run; it does not cover every research decision or arbitrary long-memory dependence. IC is not trading P&L.

## Recovery and limits

Run with --stop-after frozen, then --resume to demonstrate stage recovery. Identical completed resumes return saved metrics. Changed inputs, source, tracked artifacts or broken lineage are rejected. Fingerprints detect accidental inconsistencies, not a malicious actor who can rewrite every local file. A crash during an unsealed stage requires a fresh output directory; only sealed stages are restartable.

No model, paid API, Qlib runtime, broker, company dataset or secret is used. Synthetic relationships and the chosen small search space limit every economic conclusion. See METHODS and WALKTHROUGH for the complete interpretation.
"""
    put("REPORT.md", report.encode())
    seal("complete")
    return metrics
