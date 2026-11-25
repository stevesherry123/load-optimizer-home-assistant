"""Classify legacy EV ownership without granting command authority."""
from datetime import datetime

FORMAT = 2


def switch_target(value):
    return isinstance(value, str) and value.startswith('switch.') and len(value) > 7 and not any(c.isspace() for c in value)


def valid_session(value):
    if not isinstance(value, dict) or type(value.get('owned')) is not bool:
        return False
    if value.get('phase') not in ('idle', 'starting', 'charging', 'stopping', 'blocked'):
        return False
    if type(value.get('requires_review')) is not bool or not isinstance(value.get('reason'), str):
        return False
    pending = value.get('pending')
    if pending is None:
        return True
    if not isinstance(pending, dict) or pending.get('action') not in ('start', 'stop') or not isinstance(pending.get('id'), str):
        return False
    try:
        issued, deadline = (datetime.fromisoformat(pending[key]) for key in ('issued', 'deadline'))
        return bool(issued.tzinfo and deadline.tzinfo and deadline > issued)
    except (KeyError, TypeError, ValueError):
        return False


def legacy_review(record, configured_target):
    """Return a review hold; only a known target can later reconcile as stopped."""
    if isinstance(record, dict) and set(record) == {'owned_target'}:
        target = record['owned_target']
        if target is None or switch_target(target):
            return {'reason': 'legacy_journal_requires_review' if target in (None, configured_target)
                    else 'ownership_target_changed', 'original_target': target,
                    'can_confirm_stopped': target in (None, configured_target)}
    if valid_session(record):
        return {'reason': 'legacy_target_unknown', 'original_target': None, 'can_confirm_stopped': False}
    return {'reason': 'legacy_journal_unrecognized', 'original_target': None, 'can_confirm_stopped': False}
