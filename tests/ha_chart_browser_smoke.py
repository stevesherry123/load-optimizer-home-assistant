"""Optional real-card render check; requires Playwright, Chrome and the official card asset."""

import asyncio
import json
import os
from pathlib import Path
from datetime import datetime, timezone, timedelta
import yaml
from playwright.async_api import async_playwright

ROOT=Path(__file__).resolve().parents[1]
data=yaml.safe_load((ROOT/'homeassistant/dashboards/full/load_optimizer_dashboard.yaml').read_text())
def find(value):
    if isinstance(value,dict):
        if value.get('header',{}).get('title')=='Octopus Prices': yield value
        for item in value.values(): yield from find(item)
    elif isinstance(value,list):
        for item in value: yield from find(item)
charts=list(find(data))
asset=Path(os.environ['LOAD_OPTIMIZER_APEX_CARD']).read_text()
async def main():
    async with async_playwright() as p:
        browser=await p.chromium.launch(executable_path=os.environ.get('LOAD_OPTIMIZER_CHROME'),headless=True)
        try:
            for zone in ['America/New_York','Europe/London']:
                for preference in ['local','server']:
                    width=int(os.environ.get('LOAD_OPTIMIZER_CHART_WIDTH','1200'))
                    context=await browser.new_context(timezone_id=zone,viewport={'width':width,'height':650})
                    await context.route('http://chart.test/**',lambda route:route.fulfill(body='<!doctype html><html><head><style>body{font-family:Arial;background:white;color:#222}apexcharts-card{display:block;max-width:1100px;width:calc(100vw - 16px)}</style></head><body></body></html>',content_type='text/html'))
                    page=await context.new_page()
                    errors=[]
                    page.on('pageerror',lambda error:errors.append(str(error)))
                    await page.goto('http://chart.test/')
                    await page.clock.set_fixed_time(datetime(2026,10,26,12,tzinfo=timezone.utc))
                    await page.add_script_tag(content=asset,type='module')
                    await page.wait_for_function("Boolean(customElements.get('apexcharts-card'))")
                    for chart in charts:
                        chart=dict(chart)
                        chart.pop('visibility',None)
                        chart.pop('grid_options',None)
                        start=datetime(2026,10,26,tzinfo=timezone.utc)
                        count=96 if chart['graph_span']=='48h' else 48
                        rates=[{'start':(start+timedelta(minutes=30*i)).isoformat(),'end':(start+timedelta(minutes=30*(i+1))).isoformat(),'price_p_per_kwh':-5+(i%36)} for i in range(count)]
                        end=(start+timedelta(minutes=30*count)).isoformat()
                        def state(entity_id,value,attrs): return {'entity_id':entity_id,'state':value,'attributes':attrs,'last_changed':start.isoformat(),'last_updated':start.isoformat(),'context':{'id':'test','parent_id':None,'user_id':None}}
                        states={
                            'sensor.load_optimizer_status':state('sensor.load_optimizer_status','ready',{}),
                            'sensor.load_optimizer_1_cost_status':state('sensor.load_optimizer_1_cost_status','ready',{'tariff_entities':['event.test_rates'],'tariff_timezone':'Europe/London','tariff_start':start.isoformat(),'tariff_end':end}),
                            'sensor.load_optimizer_1_tariff_horizon':state('sensor.load_optimizer_1_tariff_horizon',chart['graph_span'],{}),
                            'event.test_rates':state('event.test_rates','ready',{'rates':rates}),
                            'sensor.load_optimizer_ofgem_price_cap_benchmark':state('sensor.load_optimizer_ofgem_price_cap_benchmark','25',{'unit_of_measurement':'p/kWh','references':[{'effective_from_utc':start.isoformat(),'effective_to_utc':end,'unit_rate_p_per_kwh':25}]}),
                        }
                        await page.evaluate('''({config,states,preference})=>{
                          document.querySelector('apexcharts-card')?.remove();
                          const card=document.createElement('apexcharts-card');
                          card.setConfig(config);
                          card.hass={states,config:{time_zone:'Europe/London'},locale:{time_zone:preference,language:'en-GB',number_format:'language',time_format:'24'},language:'en',themes:{darkMode:false},callApi:async()=>[],callWS:async()=>[]};
                          document.body.append(card);window.testCard=card;
                        }''',{'config':chart,'states':states,'preference':preference})
                        await page.wait_for_function("window.testCard.shadowRoot?.querySelectorAll('.apexcharts-series path').length > 2",timeout=20000)
                        await page.wait_for_timeout(500)
                        result=await page.evaluate('''()=>{const card=window.testCard;return {min:card._apexChart.w.config.xaxis.min,max:card._apexChart.w.config.xaxis.max,series:card._apexChart.w.config.series.map(x=>x.data.slice(0,2)),labels:[...card.shadowRoot.querySelectorAll('.apexcharts-xaxis-label')].map(x=>x.textContent),now:card.shadowRoot.textContent.includes('Now (tariff time)'),svg:card.shadowRoot.querySelector('svg').getBoundingClientRect().toJSON()}}''')
                        assert result['min']==start.timestamp()*1000,result
                        assert result['max']==datetime.fromisoformat(end).timestamp()*1000,result
                        assert result['series'][0][0][0]==start.timestamp()*1000,result
                        assert any('00:00' in x for x in result['labels']),result
                        assert result['now'],result
                        assert result['svg']['right'] <= width,result
                        assert not errors,errors
                        name=f"/private/tmp/lo-chart-{zone.replace('/','-')}-{preference}-{chart['graph_span']}-{width}.png"
                        await page.screenshot(path=name)
                        print(zone,preference,chart['graph_span'],json.dumps(result),name)
                    await context.close()
        finally:
            await browser.close()
asyncio.run(main())
