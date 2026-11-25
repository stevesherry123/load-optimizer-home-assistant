"""Read-only chronological replay of retained learned-cycle estimates.

Older aggregate sums are reconstructed by subtracting retained cycles. Every
prediction uses only that older aggregate and earlier retained cycles; the
current/future cycle never contributes. No model or HA state is changed.
"""
from __future__ import annotations
import argparse
import json
import math
from datetime import datetime, timezone
from pathlib import Path
from statistics import mean

FIELDS = ('runtime_minutes', 'energy_kwh')


def replay_model(model: dict, window: int = 5) -> dict:
    if window < 2:
        raise ValueError('Recent window must contain at least two runs')
    cycles = model.get('recent_cycles', [])
    try:
        stamps = [datetime.fromisoformat(row['finish']) for row in cycles]
        if any(stamp.tzinfo is None for stamp in stamps):
            raise ValueError('Finish times need timezones')
        stamps = [stamp.astimezone(timezone.utc) for stamp in stamps]
    except (KeyError, TypeError, ValueError) as error:
        raise ValueError('Retained runs need valid timezone-aware finish times') from error
    if stamps != sorted(set(stamps)):
        raise ValueError('Retained runs must have unique chronological finish times')
    report = {'retained_runs': len(cycles), 'recent_window': window, 'metrics': {}}
    for field in FIELDS:
        values = [row.get(field) for row in cycles]
        if any(type(value) not in (int, float) or not math.isfinite(value) or value <= 0 for value in values):
            raise ValueError('Retained runs need finite positive measurements')
        stat = model.get('statistics', {}).get(field, {})
        count, average = stat.get('count'), stat.get('mean')
        if type(count) is not int or count < len(values) or type(average) not in (int, float) or not math.isfinite(average):
            raise ValueError('Aggregate statistics do not cover retained runs')
        older_count = count - len(values)
        older_sum = count * average - math.fsum(values)
        if older_sum < -1e-8 or older_count == 0 and abs(older_sum) > 1e-8:
            raise ValueError('Aggregate and retained measurements disagree')
        older_sum = max(0.0, older_sum)
        rows = []
        for index in range(window, len(values)):
            history = values[:index]
            baseline = (older_sum + math.fsum(history)) / (older_count + index)
            recent = mean(history[-window:])
            actual = values[index]
            rows.append({'all_history': baseline, 'recent': recent, 'actual': actual})
        metric = {'holdout_runs': len(rows)}
        for method in ('all_history', 'recent'):
            metric[method] = {
                'mean_absolute_error': mean(abs(row[method] - row['actual']) for row in rows) if rows else None,
                'mean_signed_error': mean(row[method] - row['actual'] for row in rows) if rows else None,
                'mean_absolute_percent_error': mean(abs(row[method] / row['actual'] - 1) * 100 for row in rows) if rows else None,
            }
        report['metrics'][field] = metric
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('storage', type=Path)
    parser.add_argument('--instance', default='1')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    raw = json.loads(args.storage.read_text())
    instance = raw.get('data', raw)['instances'][args.instance]
    reports, excluded = {}, {}
    for program, model in instance.get('program_models', {}).items():
        try:
            reports[program] = replay_model(model)
        except ValueError as error:
            excluded[program] = str(error)
    output = {'method': 'fixed five-run mean versus reconstructed prior all-history mean',
              'limitations': ['Small retained holdout; not sufficient for automatic calibration promotion.',
                              'Historical option groups and meter-counter deltas are not retained for every cycle.',
                              'Replay uses recorded learned energy, not independently verified billed energy.'],
              'programs': reports, 'excluded': excluded}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(output, indent=2) + '\n')
    args.output.chmod(0o600)
    print('Read-only replay saved; no learning data or runtime settings changed.')


if __name__ == '__main__':
    main()
