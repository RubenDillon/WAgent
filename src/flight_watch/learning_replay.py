"""Fase 1: reproduce offline una grabación del Recorder (data/diagnostics/learning/job_N) con el código actual.
Uso: python -m flight_watch.learning_replay data/diagnostics/learning/job_38 [--goal goal.json]
Por cada paso: re-anota semántica, recalcula estado y acción determinista, y la compara con lo grabado. No abre navegador ni llama al LLM."""
from __future__ import annotations
import argparse,json
from collections import Counter
from pathlib import Path
from . import form_mapper
from .flight_harness import enrich
from .learning_agent import auto_action
from .semantic_forms import annotate,form_summary,role_state
GOAL={'origin':'EZE','destination':'FCO','departure':'2027-07-17','return_date':'2027-07-29','ages':[30,30],'cabin':'ECONOMY'}
def replay_step(path,goal):
 d=json.loads(Path(path).read_text(encoding='utf-8'));obs=d['observation'];els=annotate(obs.get('elements',[]));obs['role_state']=role_state(els);obs['form_summary']=form_summary(els)
 obs.setdefault('full_text','');x=enrich(obs,goal,(),obs.get('start_url',''),());state=x['harness']['state'];m=form_mapper.heuristic_map(x)
 act=auto_action(state,x,goal,m,Counter())
 return {'file':Path(path).name,'url':(obs.get('url') or '')[:80],'recorded_state':d.get('state'),'state':state,'auto_action':act,'recorded_action':d.get('action'),'roles':{k:v['id'] for k,v in m.items()},'elements':len(els)}
def replay(directory,goal=None):return [replay_step(p,goal or GOAL) for p in sorted(Path(directory).glob('step_*.json'))]
def main():
 ap=argparse.ArgumentParser();ap.add_argument('dir');ap.add_argument('--goal');a=ap.parse_args();goal=json.loads(Path(a.goal).read_text()) if a.goal else GOAL
 for r in replay(a.dir,goal):
  flag='  ' if r['state']==r['recorded_state'] else '≠ ';print(f"{flag}{r['file']} {r['recorded_state']}→{r['state']} · {r['elements']} el · roles={r['roles']}\n     auto={json.dumps(r['auto_action'],ensure_ascii=False)}\n     grabada={json.dumps(r['recorded_action'],ensure_ascii=False)}")
if __name__=='__main__':main()
