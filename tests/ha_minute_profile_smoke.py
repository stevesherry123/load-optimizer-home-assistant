"""Actual HA storage/reload of a legacy model and richer learned profiles."""
import asyncio
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from homeassistant import loader
from homeassistant.bootstrap import async_from_config_dict
from homeassistant.core import HomeAssistant
from custom_components.load_optimizer.legacy_runtime import LegacyRuntime
from custom_components.load_optimizer.legacy import app_runtime
from test_minute_profiles import cycle


async def main():
    with TemporaryDirectory() as directory:
        hass = HomeAssistant(directory)
        hass.config.skip_pip = True
        loader.async_setup(hass)
        try:
            with patch('homeassistant.bootstrap.DEFAULT_INTEGRATIONS', set()):
                await async_from_config_dict({'homeassistant': {'time_zone': 'Europe/London'}}, hass)
            instance = {'runs': 5}
            for index in range(5): app_runtime.update_program_model(instance, cycle(index))
            instance['last_cycle'] = cycle(4)
            for row in instance['program_models']['Eco50']['recent_cycles']:
                row.pop('minute_energy_profile')
            before = deepcopy(instance['program_models']['Eco50']['statistics'])
            runtime = LegacyRuntime(hass)
            await runtime.store.async_save({'schema_version': 1, 'instances': {'1': instance}})
            hass.states.async_set('sensor.synthetic_power', '0')
            options = {'instances': [{'id': '1', 'name': 'Synthetic dishwasher', 'power_sensor': 'sensor.synthetic_power'}]}
            first = await runtime.async_scan(options)
            model = first.entities['sensor.load_optimizer_1_program_model']['attributes']
            assert model['power_profile_basis'] == 'legacy_point_fallback'
            assert model['minute_profile_sample_count'] == 1
            assert runtime.state['instances']['1']['program_models']['Eco50']['statistics'] == before
            assert runtime.state['instances']['1']['runs'] == 5
            # Learning is pure worker-side computation; no device service is called.
            def learn():
                instance = runtime.state['instances']['1']
                for index in range(5, 9):
                    record = cycle(index)
                    app_runtime.update_program_model(instance, record)
                    instance['last_cycle'] = record
                    instance['runs'] += 1
            await hass.async_add_executor_job(learn)
            result = await runtime.async_scan(options)
            model = result.entities['sensor.load_optimizer_1_program_model']['attributes']
            assert model['power_profile_basis'] == 'minute_energy_v1'
            assert model['minute_profile_sample_count'] == 5
            assert model['profile_format'] == ['progress_percent', 'power_w']
            assert max(y for x, y in model['representative_profile'] if 35 < x < 43) > 1000
            chart = result.entities['sensor.load_optimizer_1_profile_data']['attributes']
            assert chart['program_profiles'][0]['power_profile_basis'] == 'minute_energy_v1'
            assert len(chart['program_profiles'][0]['points']) <= 360
            expected = deepcopy(runtime.state)
            # A new adapter reads the actual persisted HA Store and retains the exact model.
            restored = LegacyRuntime(hass)
            await restored.async_load()
            assert restored.state == expected
            await restored.async_scan(options)
            assert restored.state['instances']['1']['runs'] == 9
            assert app_runtime.program_summary('Eco50', restored.state['instances']['1']['program_models']['Eco50'])['power_profile_basis'] == 'minute_energy_v1'
            # Capture options and raw counters through real HA source states, not
            # just by constructing a completed-cycle dictionary.
            class Clock(datetime):
                current = datetime.now(timezone.utc)
                @classmethod
                def now(cls, tz=None):
                    return cls.current.astimezone(tz) if tz else cls.current.replace(tzinfo=None)
            capture_options = {'instances': [{'id': '2', 'name': 'Capture bench',
                'power_sensor': 'sensor.capture_power', 'energy_sensor': 'sensor.capture_energy',
                'program_sensor': 'sensor.capture_program', 'state_sensor': 'sensor.capture_state'}]}
            key = 'Dishcare.Dishwasher.Option.ExtraDry'
            with patch('custom_components.load_optimizer.legacy_runtime.datetime', Clock):
                for minute in range(7):
                    hass.states.async_set('sensor.capture_power', 30 if minute < 6 else 0)
                    hass.states.async_set('sensor.capture_energy', minute * .0005)
                    hass.states.async_set('sensor.capture_program', 'Eco50', {'program_options': {key: True}} if minute else {})
                    hass.states.async_set('sensor.capture_state', 'Running' if minute < 6 else 'Finished')
                    await restored.async_scan(capture_options)
                    Clock.current += timedelta(minutes=1)
            captured = restored.state['instances']['2']['last_cycle']
            assert captured['program_options'] == {'status': 'observed', 'values': {key: True}}
            assert captured['start'] and captured['energy_sensor_delta_kwh'] == .003
            row = restored.state['instances']['2']['program_models']['Eco50']['recent_cycles'][-1]
            assert row['minute_energy_profile']['version'] == 1
            assert row['program_options'] == captured['program_options']
            print('Real HA: legacy fallback, exact retained-capture recovery, five-profile promotion, bounded step charts and persisted reload passed; no physical device commands')
        finally:
            await hass.async_stop(force=True)


if __name__ == '__main__':
    asyncio.run(main())
