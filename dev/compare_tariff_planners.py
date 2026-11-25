"""Compare exact planner outputs and warm median timings using synthetic prices."""

from argparse import ArgumentParser
from datetime import datetime, timedelta, timezone
from hashlib import sha256
from json import dumps
from pathlib import Path
from runpy import run_path
from statistics import median
from time import perf_counter


def cases():
    for title, reference, spacing, count, horizon, confidence in (
        ("normal-48h", datetime(2026, 11, 18, 16, tzinfo=timezone.utc), 30, 96, 24, 84),
        ("autumn-DST-and-free", datetime(2026, 10, 24, 16, tzinfo=timezone.utc), 30, 100, 24, 80),
        ("quarter-hour-with-gap", datetime(2026, 3, 28, 16, tzinfo=timezone.utc), 15, 192, 30, 88),
    ):
        models = []
        policies = []
        for index, runtime in enumerate((30, 52.3, 65, 112.45, 160, 243.7)):
            program = "Synthetic" + str(index)
            models.append(dict(program=program, expected_runtime_minutes=runtime,
                               expected_energy_kwh=0.48 + index / 9, confidence=confidence + index,
                               representative_profile_w=[110 + (step * 67 % 2200) for step in range(37)],
                               recent_cycles=[]))
            policies.append(dict(program=program, enabled=True, allow_normal_recommendation=True,
                                 allow_negative_price_run=index % 2 == 0, preference_rank=50 + index,
                                 consumables_cost_pence=1.1 + index / 2, wear_cost_pence=0.5))
        periods = [dict(start=reference + timedelta(minutes=index * spacing),
                        end=reference + timedelta(minutes=(index + 1) * spacing),
                        price_p_per_kwh=float(10 + 3 * (index % 17) if title == "normal-48h"
                                             else -5 if 8 <= index < 15 else 3 * (index % 17) - 2))
                   for index in range(count) if title != "quarter-hour-with-gap" or index != 31]
        if title == "autumn-DST-and-free":
            periods[16].update(price_p_per_kwh=0, source="free_electricity_calendar")
            periods[17].update(price_p_per_kwh=-10, source="manual_special_price_window")
        options = dict(reference_utc=reference, search_hours=horizon, forecast_hours=horizon + 6,
                       candidate_interval_minutes=5, forecast_interval_minutes=15, schedule_timezone="Europe/London",
                       blocked_windows=[dict(start=reference + timedelta(hours=4),
                                             end=reference + timedelta(hours=5))],
                       green_windows=[dict(start=reference + timedelta(hours=7),
                                           end=reference + timedelta(hours=9))])
        yield title, (models, policies, periods), options


def planner(root):
    path = Path(root) / "custom_components/load_optimizer/legacy/costing.py"
    return run_path(str(path))["recommend_cycle"]


def main():
    parser = ArgumentParser(description=__doc__)
    parser.add_argument("old")
    parser.add_argument("new")
    parser.add_argument("--repeats", type=int, default=3)
    args = parser.parse_args()
    if args.repeats < 1:
        parser.error("--repeats must be positive")
    old, new = planner(args.old), planner(args.new)
    for title, inputs, options in cases():
        expected = old(*inputs, **options)
        assert new(*inputs, **options) == expected, title
        samples = [[], []]
        implementations = (old, new)
        for repeat in range(args.repeats):
            for tag in (range(2) if repeat % 2 == 0 else range(1, -1, -1)):
                start = perf_counter()
                result = implementations[tag](*inputs, **options)
                samples[tag].append(perf_counter() - start)
                assert result == expected, title
        before, after = map(median, samples)
        signature = sha256(dumps(expected, default=str, sort_keys=True).encode()).hexdigest()[:12]
        print(f"{title}: exact result {signature}; {before:.3f}s -> {after:.3f}s ({(1 - after / before):+.1%})", flush=True)


if __name__ == "__main__":
    main()
