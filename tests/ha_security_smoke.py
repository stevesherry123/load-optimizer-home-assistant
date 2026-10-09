"""Exercise actual HA service authorization and privacy without live devices."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from homeassistant.auth.const import GROUP_ID_ADMIN
from homeassistant.bootstrap import async_from_config_dict
from homeassistant.core import Context, HomeAssistant
from homeassistant.exceptions import Unauthorized, UnknownUser
from homeassistant import loader

from custom_components.load_optimizer import async_setup
from custom_components.load_optimizer.const import DOMAIN
from custom_components.load_optimizer.diagnostics import async_get_config_entry_diagnostics
from custom_components.load_optimizer.legacy_runtime import LegacyRuntime
from custom_components.load_optimizer.price_cap import MAX_RESPONSE_BYTES, PriceCapManager


async def permissions(hass):
    assert await async_setup(hass, {})
    admin = await hass.auth.async_create_user("Security administrator", group_ids=[GROUP_ID_ADMIN])
    ordinary = await hass.auth.async_create_user("Ordinary user", group_ids=[])
    assert admin.is_admin and not ordinary.is_admin
    hass.services.async_register("persistent_notification", "create", lambda call: None)
    actions = {
        "import_legacy_state": {"legacy_state_json": '{"instances":{}}'},
        "mothball_legacy_addon": {}, "recover": {}, "prepare_orchestration_migration": {},
        "activate_native_orchestration": {}, "deactivate_native_orchestration": {},
    }
    hass.data[DOMAIN] = {}
    beta_actions = {}
    if hass.services.has_service(DOMAIN, "analyse_tariffs"):
        coordinator = SimpleNamespace(
            tariff_intelligence=SimpleNamespace(async_export=AsyncMock(return_value={}),
                                                async_import=AsyncMock(return_value={})),
            narrative=SimpleNamespace(async_generate=AsyncMock(), snapshot=Mock(return_value={"status": "disabled"})),
            data={"tariff_intelligence": {}}, async_request_refresh=AsyncMock(), async_update_listeners=Mock(),
            legacy_runtime=None, orchestrator=None, orchestration_migration=None,
        )
        hass.data[DOMAIN]["beta-security-entry"] = coordinator
        beta_actions = {
            "analyse_tariffs": {}, "export_tariff_history": {},
            "import_tariff_history": {"history_json": "{}"},
            "generate_tariff_summary": {"ai_task_entity": "ai_task.synthetic_security_test"},
        }
        actions.update({name: {"entry_id": "beta-security-entry", **data}
                        for name, data in beta_actions.items()})
    for service, data in actions.items():
        response = service in beta_actions and service != "analyse_tariffs"
        for user_id, exception in ((ordinary.id, Unauthorized), ("missing-user", UnknownUser)):
            before = list(hass.states.async_all())
            try:
                await hass.services.async_call(DOMAIN, service, data, blocking=True,
                                               context=Context(user_id=user_id), return_response=response)
            except exception:
                pass
            else:
                raise AssertionError(f"Unauthorized action allowed: {service}")
            assert list(hass.states.async_all()) == before
        await hass.services.async_call(DOMAIN, service, data, blocking=True,
                                       context=Context(user_id=admin.id), return_response=response)
        # System automations keep HA's documented administrator-service behaviour.
        await hass.services.async_call(DOMAIN, service, data, blocking=True, return_response=response)
    await hass.async_block_till_done()
    print(f"All {len(actions)} maintenance/history/AI actions reject ordinary and unknown users; admin/system calls work")


async def privacy(hass):
    secret = "PRIVATE-HOUSEHOLD-DATA"
    entry = SimpleNamespace(entry_id="security-test", title=secret,
        data={"load_type": "learned_appliance", "tariff_entity": secret, "name": secret,
              "instances_yaml": secret, "unknown_credential": secret},
        options={"bosch_device_id": secret, "tariff_entities": secret, "scan_interval": 60,
                 "instances_yaml": secret, "api_key": secret, "cost_search_hours": secret})
    hass.data[DOMAIN][entry.entry_id] = SimpleNamespace(last_update_success=True, data={
        "status": "ready", "instance_count": 3, "published_entity_count": 193,
        "legacy_entities": {secret: {"state": secret, "attributes": {secret: secret}}},
        "legacy_instances": {secret: secret}, "message": secret, "entities": secret,
        "orchestration": {"status": secret, "config": {"device_id": secret}, "last_message": secret},
        "orchestration_migration": {"status": "prepared", "helpers": secret},
        "plan": {"status": "ready", "selected_slots": secret, "battery_percent": secret},
        "tariff_intelligence": {"status": "ready", "source_id": secret, "narrative": secret},
        "price_cap": {"status": "ready", "region": secret},
    })
    original = json.dumps(hass.data[DOMAIN][entry.entry_id].data)
    result = await async_get_config_entry_diagnostics(hass, entry)
    assert secret not in json.dumps(result), result
    assert result["entry"]["options"] == {"scan_interval": 60}
    assert result["coordinator_data"]["instance_count"] == 3
    assert json.dumps(hass.data[DOMAIN][entry.entry_id].data) == original
    print("Diagnostic downloads exclude names, raw YAML, device/entity IDs, schedules, AI text and secrets")


async def imports(hass):
    runtime = LegacyRuntime(hass)
    runtime.store = SimpleNamespace(async_load=AsyncMock(return_value={"schema_version": 1, "instances": []}),
                                    async_save=AsyncMock())
    try:
        await runtime.async_load()
    except ValueError:
        pass
    else:
        raise AssertionError("Corrupt existing storage was silently replaced")
    assert runtime.state is None
    runtime.store.async_save.assert_not_awaited()
    original = {"schema_version": 1, "instances": {"1": {"runs": 114}}}
    runtime.state = original
    runtime.last_signature = "old-signature"
    runtime.store = SimpleNamespace(async_save=AsyncMock(side_effect=OSError("Synthetic disk failure")))
    payload = {"instances": {"1": {"runs": 115, "program_models": {"MixedLoad": {"runs": 4}}}}}
    try:
        await runtime.async_import_state(payload)
    except OSError:
        pass
    else:
        raise AssertionError("Simulated storage failure did not occur")
    assert runtime.state is original and runtime.last_signature == "old-signature"
    runtime.store.async_save = AsyncMock()
    for invalid in ('{"instances":[]}', '{"instances":{},"extra":NaN}'):
        try:
            await runtime.async_import_state(invalid)
        except ValueError:
            pass
        else:
            raise AssertionError("Invalid import was accepted")
    runtime.store.async_save.assert_not_awaited()
    original["instances"]["1"]["cycle_start"] = "2026-10-09T12:00:00Z"
    try:
        await runtime.async_import_state(payload)
    except ValueError:
        pass
    else:
        raise AssertionError("Active capture was replaced")
    runtime.store.async_save.assert_not_awaited()
    del original["instances"]["1"]["cycle_start"]
    async with runtime._state_lock:
        task = asyncio.create_task(runtime.async_import_state(payload))
        await asyncio.sleep(0.05)
        assert not task.done() and runtime.state is original
        runtime.store.async_save.assert_not_awaited()
    await task
    assert runtime.state["instances"]["1"]["runs"] == 115
    assert runtime.state["instances"]["1"]["program_models"]["MixedLoad"]["runs"] == 4
    payload["instances"]["1"]["runs"] = 0
    assert runtime.state["instances"]["1"]["runs"] == 115
    print("Failed, malformed, concurrent and active-capture imports preserve existing memory")


class Response:
    def __init__(self, body=b"safe document", status=200, location=None):
        self.body, self.status = body, status
        self.headers = {"Location": location} if location else {}
        self.charset = "utf-8"
        self.content = self

    def raise_for_status(self):
        if self.status >= 400:
            raise ValueError("Synthetic HTTP failure")

    async def iter_chunked(self, count):
        for index in range(0, len(self.body), count):
            yield self.body[index:index + count]

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False


async def http_boundaries():
    valid = "https://www.ofgem.gov.uk/test"
    session = SimpleNamespace(get=Mock(return_value=Response()))
    assert await PriceCapManager._async_fetch_text(session, valid) == "safe document"
    assert session.get.call_args.kwargs["allow_redirects"] is False
    for url in ("http://www.ofgem.gov.uk/test", "https://127.0.0.1/test", "file:///private/test",
                "https://www.ofgem.gov.uk.evil.invalid/test", "https://user:pass@www.ofgem.gov.uk/test",
                "https://www.ofgem.gov.uk:8123/test"):
        session.get.reset_mock()
        try:
            await PriceCapManager._async_fetch_text(session, url)
        except ValueError:
            pass
        else:
            raise AssertionError("Unsafe URL was requested")
        session.get.assert_not_called()
    for response in (Response(status=302, location="http://127.0.0.1/private"),
                     Response(body=b"x" * (MAX_RESPONSE_BYTES + 1)), Response(status=204),
                     Response(status=302, location="/another-redirect")):
        session.get = Mock(return_value=response)
        try:
            await PriceCapManager._async_fetch_text(session, valid)
        except ValueError:
            pass
        else:
            raise AssertionError("Unsafe or oversized response was accepted")
        assert session.get.call_count <= 4
    session.get = Mock(side_effect=[Response(status=301, location="/moved"), Response()])
    assert await PriceCapManager._async_fetch_text(session, valid) == "safe document"
    print("External lookup rejects untrusted redirects, downgrade URLs, loops and oversized responses")


async def main():
    with tempfile.TemporaryDirectory(prefix="load-optimizer-security-") as config_dir:
        hass = HomeAssistant(config_dir)
        loader.async_setup(hass)
        try:
            assert await async_from_config_dict({"homeassistant": {"name": "Isolated security test"}}, hass) is hass
            await hass.async_start()
            await permissions(hass)
            await privacy(hass)
            await imports(hass)
            await http_boundaries()
        finally:
            await hass.async_stop()


asyncio.run(main())
