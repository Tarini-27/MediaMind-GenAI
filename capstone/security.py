"""Local application controls. Heuristics complement, never prove, injection resistance."""
import re
from dataclasses import dataclass, field
from prometheus_client import Counter, Histogram

REQUESTS=Counter('gather_runs_total','Agent runs',['outcome'])
REQUESTS.labels('success')
REQUESTS.labels('error')
TOOLS=Counter('gather_tools_total','Tool calls',['agent','tool','outcome'])
LATENCY=Histogram('gather_run_seconds','Run latency',buckets=(.1,.5,1,2,5,10,30,60,120,300))
MODEL_TOKENS=Counter('gather_model_tokens_total','Reported provider tokens',['kind'])
PERMISSIONS={'retriever':{'search_passages','get_passage'},'writer':{'get_passage'},
             'verifier':{'verify_claims','get_passage'},'publisher':{'publish_note'},'single':{'search_passages','get_passage','verify_claims'}}
INJECTION=re.compile(r'ignore (?:all |the |previous |prior )*(?:instructions|rules)|(?:system|developer)\s*(?:prompt|message)\s*:|reveal (?:the |your )?(?:api key|secret)|(?:exfiltrate|send secrets)',re.I)
SECRET=re.compile(r'(?i)(?:AIza[\w-]{20,}|sk-[\w-]{15,}|AQ\.[\w-]{20,}|(?:api[_ -]?key|authorization)\s*[:=]\s*\S+)')

def scrub(value):
    if isinstance(value,str):return SECRET.sub('[REDACTED]',value)
    if isinstance(value,dict):return {k:scrub(v) for k,v in value.items() if k not in {'api_key','openrouter_key'}}
    if isinstance(value,list):return [scrub(v) for v in value]
    return value

@dataclass
class Budget:
    limit:int=16
    calls:int=0
    model_calls:int=0
    max_model_calls:int=10
    tokens:int=0
    max_tokens:int=18000
    trace:list=field(default_factory=list)

    def tool(self,agent,tool,args):
        if tool not in PERMISSIONS.get(agent,set()):
            TOOLS.labels(agent,tool,'denied').inc()
            raise ValueError('This specialist is not permitted to use that tool.')
        if self.calls>=self.limit:raise ValueError('Tool budget exhausted.')
        self.calls+=1
        self.trace.append({'agent':agent,'tool':tool,'arguments':scrub(args)})

    def before_model(self):
        if self.model_calls>=self.max_model_calls or self.tokens>=self.max_tokens:
            raise ValueError('Model budget exhausted.')
        self.model_calls+=1

    def usage(self,usage):
        for kind in ('prompt_tokens','completion_tokens'):
            n=max(0,int(usage.get(kind,0)))
            self.tokens+=n
            MODEL_TOKENS.labels(kind).inc(n)
