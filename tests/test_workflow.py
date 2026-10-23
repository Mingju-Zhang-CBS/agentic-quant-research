import copy
import json
import numpy as np
import pandas as pd
import pytest
from agentic_quant_research.core import (admit, bootstrap_interval, calculate_factor, date_split,
    default_proposals, generate_market, run_workflow, validate_expression, validate_market, verify_lineage)


@pytest.fixture
def panel():
    return validate_market(generate_market(assets=5, sessions=180, seed=91))


def test_admission_keeps_duplicate_and_invalid_outcomes_visible():
    rows, accepted = admit(default_proposals())
    assert rows.status.tolist() == ['ADMITTED'] * 3 + ['DUPLICATE', 'REJECTED', 'REJECTED']
    assert len(accepted) == 3
    assert 'momentum20' in rows.iloc[3].reason
    with pytest.raises(ValueError):
        admit([default_proposals()[0]] * 2)


@pytest.mark.parametrize('expression', [
    {'op': 'lag', 'field': 'close', 'window': -1},
    {'op': 'return', 'field': 'close', 'window': True},
    {'op': 'return', 'field': 'label', 'window': 1},
    {'op': '__import__', 'field': 'close', 'window': 1},
    {'op': 'return', 'field': 'close', 'window': 5, 'code': 'arbitrary'},
])
def test_expression_contract_rejects_future_and_arbitrary_execution(expression):
    with pytest.raises(ValueError):
        validate_expression(expression)


def test_market_rejects_duplicates_missing_keys_and_bad_ohlc(panel):
    for bad in [pd.concat([panel, panel.iloc[:1]]), panel.drop(index=0), panel.assign(close=np.inf)]:
        with pytest.raises(ValueError):
            validate_market(bad)
    broken = panel.copy(); broken.loc[0, 'high'] = broken.loc[0, 'low'] / 2
    with pytest.raises(ValueError):
        validate_market(broken)


def test_factor_uses_only_available_history(panel):
    expr = default_proposals()[0]['expression']
    result = calculate_factor(panel, expr)
    modified = panel.copy(); boundary = modified.date.unique()[100]
    modified.loc[modified.date > boundary, 'close'] *= 5
    later = calculate_factor(modified, expr)
    pd.testing.assert_series_equal(result[panel.date <= boundary], later[panel.date <= boundary])
    asset = panel.asset.iloc[0]; group = panel[panel.asset == asset]
    assert result[group.index[20]] == pytest.approx(group.close.iloc[20] / group.close.iloc[0] - 1)


def test_label_end_purge_prevents_cross_partition_targets(panel):
    _, accepted = admit(default_proposals())
    factors = pd.DataFrame({p['id']: calculate_factor(panel, p['expression']) for p in accepted})
    labels, masks, split = date_split(panel, factors)
    dates = pd.Series(panel.date.unique())
    positions = panel.date.map(pd.Series(np.arange(len(dates)), index=dates))
    for name, boundary in [('train', split['first_validation']), ('validation', split['first_confirmation'])]:
        last_label_end = positions[masks[name]].max() + 5
        assert dates.iloc[last_label_end] < pd.Timestamp(boundary)
    sets = [set(panel.date[mask]) for mask in masks.values()]
    assert not (sets[0] & sets[1] or sets[0] & sets[2] or sets[1] & sets[2])
    assert np.isfinite(labels[masks['confirmation']]).all()


def test_freeze_ignores_confirmation_outcomes_and_moments_fit_train(panel, tmp_path):
    proposals = default_proposals()
    run_workflow(panel, proposals, tmp_path / 'a', stop_after='frozen')
    frozen = json.loads((tmp_path / 'a/freeze.json').read_text())
    changed = panel.copy(); boundary = pd.Timestamp(frozen['split']['first_confirmation'])
    affected = changed.date >= boundary
    changed.loc[affected, ['open','high','low','close']] *= 3
    run_workflow(changed, proposals, tmp_path / 'b', stop_after='frozen')
    other = json.loads((tmp_path / 'b/freeze.json').read_text())
    assert frozen == other
    _, accepted = admit(proposals)
    factors = pd.DataFrame({p['id']: calculate_factor(panel,p['expression']) for p in accepted})
    _, masks, _ = date_split(panel, factors)
    for name, moments in frozen['preprocessing'].items():
        assert moments['mean'] == pytest.approx(factors.loc[masks['train'],name].mean())


def test_sealed_resume_preserves_freeze_and_completed_metrics(panel, tmp_path):
    out = tmp_path / 'run'; proposals = default_proposals()
    result = run_workflow(panel, proposals, out, stop_after='frozen')
    assert result['stage'] == 'frozen' and not (out / 'metrics.json').exists()
    before = (out / 'freeze.json').read_bytes()
    metrics = run_workflow(panel, proposals, out, resume=True)
    assert before == (out / 'freeze.json').read_bytes()
    lineage = (out / 'lineage.jsonl').read_bytes()
    assert metrics == run_workflow(panel, proposals, out, resume=True)
    assert (out / 'lineage.jsonl').read_bytes() == lineage
    assert verify_lineage(out / 'lineage.jsonl')
    with pytest.raises(ValueError):
        run_workflow(panel, proposals, out)
    different = copy.deepcopy(proposals); different[0]['hypothesis'] += ' changed'
    with pytest.raises(ValueError, match='identity'):
        run_workflow(panel, different, out, resume=True)


def test_artifact_and_lineage_tampering_fail_closed(panel, tmp_path):
    out = tmp_path / 'artifact'
    run_workflow(panel, default_proposals(), out, stop_after='admitted')
    (out / 'admission.csv').write_text('changed')
    with pytest.raises(ValueError, match='integrity'):
        run_workflow(panel, default_proposals(), out, resume=True)
    out = tmp_path / 'chain'
    run_workflow(panel, default_proposals(), out, stop_after='admitted')
    record = json.loads((out / 'lineage.jsonl').read_text()); record['stage'] = 'complete'
    (out / 'lineage.jsonl').write_text(json.dumps(record))
    with pytest.raises(ValueError, match='integrity'):
        run_workflow(panel, default_proposals(), out, resume=True)


def test_block_bootstrap_is_deterministic_and_rejects_invalid_values():
    assert bootstrap_interval(np.ones(40)) == [1., 1.]
    for values in [[1, 2], [np.nan] * 30, np.ones((30, 1))]:
        with pytest.raises(ValueError):
            bootstrap_interval(values)
