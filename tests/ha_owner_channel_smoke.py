"""Exercise real HA update comparisons behind the owner deployment guard."""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from homeassistant.components.update import UpdateEntity
from dev.check_owner_channel import validate_snapshot, REPOSITORY, REPOSITORY_ID


class Offer(UpdateEntity):
    def __init__(self, installed, available):
        self._attr_installed_version = installed
        self._attr_latest_version = available


def main():
    tag = 'v1.7.0-beta.12'
    raw_commit = Offer('da92d6cab8a0f30435dc03a30d75d52b46f8121b', 'v1.5.9')
    assert raw_commit.state == 'on', 'A raw commit on stable reproduces the offered replacement'
    numbered = Offer(tag, 'v1.5.9')
    assert numbered.state == 'off', 'Recognized version numbering prevents an older release appearing newer'
    # Even an off entity is insufficient: an explicit generic service call can
    # still select available_version. Channel and target must also be aligned.
    snapshot = {
        'ha_state': 'RUNNING', 'entries_loaded': True, 'provider': 'marketplace',
        'manifest_version': tag[1:],
        'repository': {'id': REPOSITORY_ID, 'full_name': REPOSITORY, 'installed': True,
            'installed_version': tag, 'available_version': 'v1.5.9', 'beta': False,
            'version_or_commit': 'version', 'pending_upgrade': False, 'update_entity_id': 'update.synthetic'},
        'update': {'entity_id': 'update.synthetic', 'state': numbered.state, 'attributes': {
            'installed_version': tag, 'latest_version': 'v1.5.9', 'in_progress': False}},
    }
    assert validate_snapshot(tag, snapshot)
    snapshot['repository'].update(beta=True, available_version=tag)
    snapshot['update']['attributes']['latest_version'] = tag
    assert Offer(tag, tag).state == 'off'
    assert validate_snapshot(tag, snapshot) == []
    print('Real HA: raw commit offers older stable; numbered beta plus matching channel/target closes the gap without any install calls')


if __name__ == '__main__':
    main()
