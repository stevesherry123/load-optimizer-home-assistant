"""Energy-preserving elapsed-minute profiles, with bounded capture validation."""
import math

VERSION = 1
MAX_SECONDS = 24 * 3600
MAX_GAP_SECONDS = 180


def _number(value):
    try:
        return type(value) in (int, float) and math.isfinite(value)
    except OverflowError:
        return False


def validate(profile):
    if not isinstance(profile, dict) or type(profile.get('version')) is not int or profile['version'] != VERSION:
        return False
    duration = profile.get('duration_seconds')
    energy = profile.get('energy_wh')
    return (bool(_number(duration) and 0 < duration <= MAX_SECONDS)
            and isinstance(energy, list) and len(energy) == math.ceil(duration / 60)
            and all(_number(e) and e >= 0 for e in energy)
            and math.isfinite(sum(energy)) and sum(energy) > 0)


def capture(cycle):
    """Integrate the recorded linear power curve; never bridge a long gap."""
    if any(cycle.get(k) for k in ('learning_excluded', 'power_source_gap', 'exclusion_reason', 'program_options_changed')):
        return None
    points = cycle.get('power_profile')
    if not isinstance(points, list) or len(points) < 2:
        return None
    clean = []
    for point in points:
        if not isinstance(point, dict):
            return None
        stamp, power = point.get('offset_seconds'), point.get('power_w')
        if not (_number(stamp) and _number(power) and stamp >= 0 and power >= 0):
            return None
        if clean and not 0 < stamp - clean[-1][0] <= MAX_GAP_SECONDS:
            return None
        clean.append((stamp, power))
    duration = clean[-1][0]
    runtime = cycle.get('runtime_minutes')
    if clean[0][0] != 0 or not 0 < duration <= MAX_SECONDS:
        return None
    if not _number(runtime) or abs(runtime * 60 - duration) > 90:
        return None
    energy = [0.0] * math.ceil(duration / 60)
    for (start, first), (end, last) in zip(clean, clean[1:]):
        cursor = start
        while cursor < end:
            index = int(cursor // 60)
            stop = min(end, (index + 1) * 60)
            left = first + (last - first) * (cursor - start) / (end - start)
            right = first + (last - first) * (stop - start) / (end - start)
            energy[index] += (left + right) / 2 * (stop - cursor) / 3600
            cursor = stop
    # Six decimal places in Wh retain energy to much better than sensor precision.
    energy = [round(e, 6) for e in energy]
    total = sum(energy) / 1000
    measured = cycle.get('energy_kwh')
    if not (_number(measured) and measured > 0 and math.isfinite(total) and total > 0
            and abs(total - measured) <= .0001):
        return None
    return {'version': VERSION, 'duration_seconds': duration, 'energy_wh': energy,
            'source': 'captured_power', 'source_sample_count': len(clean),
            'max_gap_seconds': max(b[0] - a[0] for a, b in zip(clean, clean[1:]))}


def forecast(profiles, duration_seconds, energy_kwh):
    """Average cumulative-energy curves on the predicted duration, preserving area.

    Recorded profiles stay in elapsed minutes. Only the forecast's duration is
    aligned; using cumulative energy keeps a short pulse even between bin edges.
    """
    if not profiles or not all(validate(profile) for profile in profiles):
        return None
    if not (_number(duration_seconds) and 0 < duration_seconds <= MAX_SECONDS
            and _number(energy_kwh) and energy_kwh > 0):
        return None
    edges = list(range(0, math.ceil(duration_seconds / 60) * 60, 60)) + [duration_seconds]
    result = [0.0] * (len(edges) - 1)
    for profile in profiles:
        source_duration = profile['duration_seconds']
        energy = profile['energy_wh']
        cumulative = [0.0]
        for value in energy:
            cumulative.append(cumulative[-1] + value)
        def at(stamp):
            if stamp >= source_duration:
                return cumulative[-1]
            index = min(int(stamp // 60), len(energy) - 1)
            width = min(60, source_duration - index * 60)
            return cumulative[index] + energy[index] * (stamp - index * 60) / width
        previous = 0.0
        for i, edge in enumerate(edges[1:]):
            current = at(edge * source_duration / duration_seconds)
            result[i] += max(0, current - previous) / len(profiles)
            previous = current
    scale = energy_kwh * 1000 / sum(result)
    result = [round(e * scale, 6) for e in result]
    return {'version': VERSION, 'duration_seconds': duration_seconds, 'energy_wh': result,
            'source': 'recent_completed_captures', 'source_profile_count': len(profiles)}


def segments(profile, expected_energy):
    if not validate(profile) or not _number(expected_energy) or expected_energy <= 0:
        raise ValueError('Invalid minute energy profile')
    scale = expected_energy * 1000 / sum(profile['energy_wh'])
    duration = profile['duration_seconds']
    return [{'offset_start': i * 60, 'offset_end': min(duration, (i + 1) * 60),
             'power_w': value * scale * 3600 / (min(duration, (i + 1) * 60) - i * 60)}
            for i, value in enumerate(profile['energy_wh'])]


def chart_points(segments, max_groups=180):
    """Bound display data with energy-weighted averages; costing keeps every bin."""
    group_size = max(1, math.ceil(len(segments) / max_groups))
    points = []
    for offset in range(0, len(segments), group_size):
        group = segments[offset:offset + group_size]
        start, end = group[0]['offset_start'], group[-1]['offset_end']
        power = sum((s['offset_end'] - s['offset_start']) * s['power_w'] for s in group) / (end - start)
        points.extend([[round(start / 60, 4), round(power, 3)], [round(end / 60, 4), round(power, 3)]])
    return points


def program_options(entity):
    """Retain only explicit numeric/boolean Home Connect option values, no raw metadata."""
    attributes = entity.get('attributes') if isinstance(entity, dict) else None
    if not isinstance(attributes, dict):
        return {'status': 'not_exposed', 'values': {}}
    raw = attributes.get('program_options')
    if not isinstance(raw, dict):
        raw = attributes.get('options')
    if not isinstance(raw, dict) or len(raw) > 16:
        return {'status': 'not_exposed', 'values': {}}
    values = {}
    for key, value in raw.items():
        if (not isinstance(key, str) or not key.startswith('Dishcare.Dishwasher.Option.')
                or len(key) > 128 or not all(c.isalnum() or c in '._' for c in key)):
            continue
        if isinstance(value, dict):
            value = value.get('value')
        if type(value) is bool or _number(value):
            values[key] = value
    return {'status': 'observed' if values else 'not_exposed', 'values': values}


def option_snapshot(value):
    values = value.get('values') if isinstance(value, dict) else None
    return program_options({'attributes': {'program_options': values}})
