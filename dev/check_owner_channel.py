"""Read-only check that an owner beta install is aligned with Marketplace updates."""
from __future__ import annotations

import argparse
import asyncio
import json
import os
from pathlib import Path
import re
import sys

REPOSITORY = 'stevesherry123/load-optimizer-home-assistant'
REPOSITORY_ID = '1290894913'


def validate_snapshot(tag: str, snapshot: dict) -> list[str]:
    """Fail closed when a generic update could replace the intended owner build."""
    if not re.fullmatch(r'v\d+\.\d+\.\d+-beta\.[1-9]\d*', tag):
        return ['Expected a numbered beta release tag; raw commits are not a deployment channel.']
    failures = []
    update = snapshot.get('update') or {}
    attrs = update.get('attributes') or {}
    repo = snapshot.get('repository') or {}
    checks = [
        (snapshot.get('ha_state') == 'RUNNING', 'Home Assistant is not fully running.'),
        (snapshot.get('entries_loaded') is True, 'Load Optimizer entries are not all loaded.'),
        (snapshot.get('provider') == 'marketplace', 'Update provider is not the reviewed Marketplace integration.'),
        (snapshot.get('manifest_version') == tag[1:], 'Loaded integration manifest differs from the expected release.'),
        (repo.get('id') == REPOSITORY_ID and repo.get('full_name') == REPOSITORY, 'Repository identity differs.'),
        (repo.get('beta') is True, 'Beta releases are disabled; the default install target can be an older stable release.'),
        (repo.get('installed') is True, 'Marketplace does not report an installed repository.'),
        (repo.get('installed_version') == tag, 'Marketplace installed version differs.'),
        (repo.get('available_version') == tag, 'Marketplace default install target differs from this release.'),
        (repo.get('version_or_commit') == 'version', 'Marketplace is tracking a commit rather than a release.'),
        (repo.get('pending_upgrade') is False, 'Marketplace reports a pending restart/upgrade.'),
        (repo.get('update_entity_id') == update.get('entity_id'), 'Repository and update entity do not match.'),
        (attrs.get('installed_version') == tag, 'Update entity installed version differs.'),
        (attrs.get('latest_version') == tag, 'A generic update would select a different version.'),
        (attrs.get('in_progress') is False, 'An install is still in progress.'),
        (update.get('state') == 'off', 'An update is offered or the update entity is unavailable.'),
    ]
    failures.extend(message for passed, message in checks if not passed)
    return failures


async def read_snapshot(base: str, token: str) -> dict:
    # Home Assistant's validation environment includes aiohttp. Offline validation
    # and the unit suite intentionally do not require it.
    import aiohttp

    async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=30)) as session:
        async def get(path):
            async with session.get(base + path, headers={'Authorization': 'Bearer ' + token}) as response:
                response.raise_for_status()
                return await response.json()

        async with session.ws_connect(base + '/api/websocket', receive_timeout=30) as websocket:
            await websocket.receive_json()
            await websocket.send_json({'type': 'auth', 'access_token': token})
            if (await websocket.receive_json()).get('type') != 'auth_ok':
                raise ValueError('Home Assistant authentication failed.')
            sequence = 0

            async def call(command, **arguments):
                nonlocal sequence
                sequence += 1
                await websocket.send_json({'id': sequence, 'type': command, **arguments})
                while True:
                    result = await websocket.receive_json()
                    if result.get('id') == sequence:
                        if result.get('success') is not True:
                            raise ValueError('Home Assistant read command failed: ' + command)
                        return result['result']

            repo = await call('marketplace/repository/info', repository_id=REPOSITORY_ID)
            registry = await call('config/entity_registry/list')
            entity_id = repo.get('update_entity_id')
            if not entity_id or not entity_id.startswith('update.'):
                raise ValueError('Marketplace returned no update entity.')
            entity = next((row for row in registry if row['entity_id'] == entity_id), {})
            entries = [entry for entry in await call('config_entries/get') if entry['domain'] == 'load_optimizer']
            if not entries:
                raise ValueError('No Load Optimizer entry is configured.')
            config = await get('/api/config')
            update = await get('/api/states/' + entity_id)
            diagnostics = await get('/api/diagnostics/config_entry/' + entries[0]['entry_id'])
            manifest = diagnostics.get('integration_manifest') or {}
            # Store only release metadata. Never include tokens, configuration,
            # the full diagnostic response, user identities or household states.
            return {
                'ha_state': config.get('state'),
                'entries_loaded': all(entry['state'] == 'loaded' for entry in entries),
                'provider': entity.get('platform'),
                'manifest_version': manifest.get('version'),
                'update': {'entity_id': entity_id, 'state': update.get('state'),
                           'attributes': {key: update.get('attributes', {}).get(key) for key in
                                          ('installed_version', 'latest_version', 'in_progress')}},
                'repository': {key: repo.get(key) for key in ('id', 'full_name', 'beta', 'installed',
                    'installed_version', 'available_version', 'version_or_commit', 'pending_upgrade', 'update_entity_id')},
            }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('tag')
    parser.add_argument('--snapshot', type=Path, help='Validate an existing redacted snapshot without network access')
    parser.add_argument('--output', type=Path, help='Save redacted channel/version evidence')
    args = parser.parse_args()
    try:
        if args.snapshot:
            snapshot = json.loads(args.snapshot.read_text())
        else:
            base = os.environ['LOAD_OPTIMIZER_HA_URL'].rstrip('/')
            token = os.environ['LOAD_OPTIMIZER_HA_TOKEN']
            if not base.startswith(('http://', 'https://')):
                raise ValueError('Home Assistant URL must use HTTP or HTTPS.')
            snapshot = asyncio.run(read_snapshot(base, token))
        failures = validate_snapshot(args.tag, snapshot)
        if args.output:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(json.dumps(snapshot, indent=2) + '\n')
    except Exception as error:
        # Exception text from HTTP clients can contain URLs. Do not echo it.
        print('Owner channel check could not complete (' + type(error).__name__ + ').', file=sys.stderr)
        return 2
    for failure in failures:
        print('FAIL: ' + failure)
    if failures:
        return 1
    print(args.tag + ': loaded version, beta channel and default update target agree; no update is offered.')
    print('This checks delivery metadata. File hashes, preserved learning and a real wash are separate acceptance checks.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
