"""Development-only lessons. Proposal -> human review -> immutable playbook."""
import argparse
import json
import os
from pathlib import Path
import app
from . import storage
from .models import Models
from .security import Budget


def reflect(record,models):
    if record.get('split')!='dev':raise ValueError('Lessons may be generated from development cases only.')
    if record.get('success'):raise ValueError('Select a failed development case.')
    suggestion=models.json('A development run failed. Propose one short reusable lesson with explicit applicability conditions. Never copy user secrets or make a blanket rule from one example. Return {"condition":"...","lesson":"..."}. This is a proposal for human review, never an automatic policy.',record)
    if not isinstance(suggestion.get('condition'),str) or not isinstance(suggestion.get('lesson'),str):raise ValueError('Invalid reflection.')
    return storage.propose_lesson(suggestion['condition'],suggestion['lesson'])


def main():
    parser=argparse.ArgumentParser()
    sub=parser.add_subparsers(dest='operation',required=True)
    sub.add_parser('list');sub.add_parser('freeze')
    proposal=sub.add_parser('reflect');proposal.add_argument('record',type=Path);proposal.add_argument('--model',required=True)
    review=sub.add_parser('review');review.add_argument('id');review.add_argument('--decision',choices=['approve','reject'],required=True);review.add_argument('--reason',required=True)
    args=parser.parse_args()
    app.init();storage.init()
    if args.operation=='reflect':
        model=Models(os.environ.get('OPENROUTER_API_KEY',''),args.model,'openrouter',Budget())
        print(reflect(json.loads(args.record.read_text()),model))
    elif args.operation=='list':
        with app.conn() as c:print(json.dumps([dict(r) for r in c.execute('SELECT * FROM lessons ORDER BY created')],indent=2))
    elif args.operation=='review':storage.review_lesson(args.id,args.decision=='approve',args.reason);print('Review recorded.')
    else:print(storage.freeze())

if __name__=='__main__':main()
