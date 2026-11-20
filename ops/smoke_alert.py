"""Trigger intentional agent errors, then verify Prometheus fires the configured alert.
Run against an isolated demo, not a shared/pilot deployment. No provider calls.
"""
import argparse
import json
import time
import urllib.request
import uuid

def fetch(url):
    with urllib.request.urlopen(url,timeout=10) as r:return json.load(r)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--api',default='http://127.0.0.1:8765');p.add_argument('--prometheus',default='http://127.0.0.1:9090');a=p.parse_args()
    ready=False
    for _ in range(30):
        data=fetch(a.prometheus+'/api/v1/query?query=gather_runs_total')
        if data.get('data',{}).get('result'):ready=True;break
        time.sleep(1)
    if not ready:raise SystemExit('Prometheus has not scraped the run counter. Start the full deployment first.')
    for _ in range(3):
        body={'run_id':uuid.uuid4().hex,'resume':{'action':'approve','approval_hash':'invalid'}}
        request=urllib.request.Request(a.api+'/api/chat',data=json.dumps(body).encode(),headers={'Content-Type':'application/json','X-App-Request':'1'})
        with urllib.request.urlopen(request,timeout=10) as response:response.read()
    for _ in range(25):
        alerts=fetch(a.prometheus+'/api/v1/alerts').get('data',{}).get('alerts',[])
        if any(x['labels'].get('alertname')=='GatherAgentErrors' and x.get('state')=='firing' for x in alerts):
            print('GatherAgentErrors is firing. Open the Prometheus Alerts page to demonstrate it.');break
        time.sleep(1)
    else:raise SystemExit('Alert did not fire within 25 seconds. Inspect Prometheus targets/rules.')
