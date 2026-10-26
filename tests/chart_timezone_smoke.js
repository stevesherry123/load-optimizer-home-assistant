const assert = require('node:assert/strict');
let input = '';
process.stdin.on('data', part => input += part);
process.stdin.on('end', () => {
  const charts = JSON.parse(input);
  const NativeDate = Date;
  global.window = {};
  const evaluate = source => Function(`return (${source.replace(/^EVAL:/, '')})`)();
  let count = 0;
  for (const now of ['2026-06-02T00:30:00Z', '2026-10-25T00:30:00Z',
      '2026-10-25T01:30:00Z', '2026-03-29T01:30:00Z', '2026-11-01T06:30:00Z']) {
    const stamp = NativeDate.parse(now);
    global.Date = class extends NativeDate {
      constructor(...args) { super(...(args.length ? args : [stamp])); }
      static now() { return stamp; }
    };
    for (const preference of ['local', 'server']) for (const chart of charts) {
      const expectedLabel = new Intl.DateTimeFormat('en-GB', {
        timeZone: 'Europe/London', weekday: 'short', hour: '2-digit', minute: '2-digit', hourCycle: 'h23'
      }).format(new Date(stamp));
      const start = stamp - 1800000;
      const end = stamp + 1800000;
      const tariff = { attributes: { tariff_timezone: 'Europe/London', tariff_entities: ['event.test_rates'],
        tariff_start: new Date(start).toISOString(), tariff_end: new Date(end).toISOString() } };
      const hass = { config: { time_zone: 'Europe/London' }, locale: { time_zone: preference }, states: {
        'sensor.load_optimizer_1_cost_status': tariff,
        'sensor.load_optimizer_1_tariff_horizon': { state: chart.graph_span },
        'event.test_rates': { attributes: { rates: [{ start: new Date(start).toISOString(),
          end: new Date(end).toISOString(), price_p_per_kwh: -4 }] } }
      } };
      const prices = Function('entity', 'hass', chart.series[0].data_generator)({}, hass);
      const offset = window.loadOptimizerTariffCardOffset;
      assert.equal(prices[0][0] - offset, start, 'Card offset must restore the real rate instant');
      const cap = Function('entity', 'hass', chart.series[1].data_generator)({ attributes: {
        references: [{ effective_from_utc: new Date(start).toISOString(),
          effective_to_utc: new Date(end).toISOString(), unit_rate_p_per_kwh: 25 }]
      } }, hass);
      assert.equal(cap[0][0] - offset, start, 'Benchmark and rate times must coincide');
      assert.equal(evaluate(chart.apex_config.xaxis.labels.formatter)('', stamp), expectedLabel);
      const tooltip = evaluate(chart.apex_config.tooltip.x.formatter)(stamp);
      assert.match(tooltip, /GMT|BST/, 'Tooltip must explicitly identify UK time');
      const range = window.loadOptimizerTariffChart;
      const londonHour = value => new Intl.DateTimeFormat('en-GB', { timeZone: 'Europe/London',
        hour: '2-digit', minute: '2-digit', hourCycle: 'h23' }).format(new Date(value));
      assert.equal(londonHour(range.start), '00:00');
      assert.equal(londonHour(range.end), '00:00');
      const days = chart.graph_span === '48h' ? 2 : 1;
      const hours = (range.end - range.start) / 3600000;
      const expectedHours = days * 24 + (now.startsWith('2026-10-25') ? 1 : now.startsWith('2026-03-29') ? -1 : 0);
      assert.equal(hours, expectedHours, 'Use tariff calendar days including DST, not browser days');
      const annotations = [];
      let updates = 0;
      const updated = evaluate(chart.apex_config.chart.events.updated);
      const instance = { w: { config: { xaxis: { min: 0, max: 1 } } },
        updateOptions(options) { this.w.config.xaxis = options.xaxis; updates++; updated(this); },
        removeAnnotation() {}, addXaxisAnnotation(value) { annotations.push(value); } };
      updated(instance);
      assert.equal(updates, 1, 'Axis adjustment must not loop recursively');
      assert.equal(annotations.at(-1).x, stamp, 'Now marker must use the same real instant');
      count++;
    }
  }
  global.Date = NativeDate;
  console.log(`${process.env.TZ}: ${count} chart cases passed for both profile settings, 24/48h, UK/US DST, price/cap alignment and Now marker`);
});
