"""Calibrate an independent judge against real human labels, never fill labels."""
import argparse
import json
from pathlib import Path

def kappa(pairs):
    if not pairs:return None
    n=len(pairs);observed=sum(a==b for a,b in pairs)/n
    labels=set(v for pair in pairs for v in pair)
    expected=sum(sum(a==label for a,b in pairs)/n*sum(b==label for a,b in pairs)/n for label in labels)
    return (observed-expected)/(1-expected) if expected<1 else None

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('labels',type=Path);args=p.parse_args()
    rows=[json.loads(x) for x in args.labels.read_text().splitlines() if x.strip()]
    pairs=[(r['human_supported'],r['judge_supported']) for r in rows if type(r.get('human_supported')) is bool and type(r.get('judge_supported')) is bool]
    if len(pairs)<20:raise SystemExit('At least 20 completed human/judge pairs are required. Blank templates are not labels.')
    print(json.dumps({'n':len(pairs),'cohen_kappa':kappa(pairs)}))
