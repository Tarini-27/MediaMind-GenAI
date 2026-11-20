"""Run the full Gather app on localhost. Original app.py remains a minimal baseline."""
import argparse
import os
from pathlib import Path
import uvicorn

if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--port',type=int,default=8765)
    parser.add_argument('--host',default='127.0.0.1')
    args=parser.parse_args()
    root=Path(__file__).resolve().parent
    from dotenv import load_dotenv
    load_dotenv(root/'.env',override=False)
    os.environ.setdefault('HF_HOME',str(root/'data'/'models'))
    os.environ.setdefault('RERANK_MODEL','cross-encoder/ms-marco-TinyBERT-L2-v2')
    uvicorn.run('capstone.api:api',host=args.host,port=args.port,log_level='warning',access_log=False)
