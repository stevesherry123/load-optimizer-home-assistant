const assert = require('node:assert/strict');
let input = '';
process.stdin.on('data', part => input += part);
process.stdin.on('end', () => {
  const chart = JSON.parse(input);
  assert.equal(chart.all_series_config.unit, 'GBP');
  assert.equal(chart.apex_config.yaxis.title.text, 'Estimated cost (£)');
  const series = chart.series.filter(item => item.type === 'line');
  assert.equal(series.length, 9);
  for (const item of series) {
    global.window = {};
    const run = Function('entity', 'hass', item.data_generator);
    for (const cost of [40, 0, -42]) {
      const points = run({ attributes: { forecast: [{ program: item.name,
        start: '2026-10-28T14:00:00Z', cost_pence: cost }] } },
      { config: { time_zone: 'Europe/London' } });
      assert.equal(points.length, 1);
      assert.equal(points[0][1], cost / 100, 'Pence must convert to the displayed GBP unit');
    }
    assert.deepEqual(run({ attributes: {} }, { config: { time_zone: 'Europe/London' } }), []);
  }
  console.log('Nine forecast series: GBP units, positive/zero/negative costs and missing data passed');
});
