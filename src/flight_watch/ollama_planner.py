from __future__ import annotations
import json,os,re,requests
from .flight_harness import instructions
HOST=os.getenv('OLLAMA_HOST','http://localhost:11434')
MODEL=os.getenv('FLIGHT_WATCH_MODEL','granite4.2:8b')
NUM_CTX=int(os.getenv('FLIGHT_WATCH_NUM_CTX','16384'))
MAX_EL=int(os.getenv('FLIGHT_WATCH_MAX_ELEMENTS','45'))
def set_model(name):
 global MODEL;MODEL=name
def available():
 try:return requests.get(HOST+'/api/tags',timeout=2).ok
 except requests.RequestException:return False
SYSTEM='''You are the browser planner of a flight-search agent. Pick exactly ONE next action as a single JSON object, no markdown.
Actions: click{target_id}, fill{target_id,value}, select{target_id,value}, press{target_id,key}, fill_airport{target_id,iata,role}, fill_date{target_id,iso,role}, wait{ms}, back, restart, fail{reason}.
Rules:
- target_id must be an integer copied from elements[].id. Never invent ids.
- harness.state is decided by Python; follow harness.guidance. Do not skip states.
- Airports: fill_airport only on editable inputs (never buttons). Dates: fill_date with an ISO date.
- Never use site/help search, content pages (route-map, destinations, explore) or promotions as booking.
- If dialogs is not empty, resolve the dialog first (prefer elements with in_modal=true).
- Do not repeat an action that did not change the page (see recent_actions); choose a different control.
- Never enter payment, identity or documents; never solve CAPTCHA. Prefer USD when a currency option exists.
- Do not output "finish": Python validates success itself.'''
ROLE_FOR_STATE={'LOCATE_FORM':('booking_entry','flight_search','origin','destination'),'SET_TRIP_TYPE':('trip_round','trip_oneway'),'SET_ORIGIN':('origin',),'SET_DESTINATION':('destination',),'SET_DEPARTURE':('departure_date',),'SET_RETURN':('return_date',),'SET_PASSENGERS':('adults','passengers'),'SET_CABIN':('cabin',),'SET_CURRENCY':('currency',),'SUBMIT':('flight_search',)}
KEEP=('id','tag','role','id_attr','name','type','href','placeholder','aria_label','label','text','value','checked','disabled','in_modal','expanded','options','semantic_hints')
BAD=('site_search','content_navigation')
def _clip(v,n):
 s=re.sub(r'\s+',' ',str(v)) if isinstance(v,str) else v
 return s[:n] if isinstance(s,str) else s
def _strength(e,wanted):
 h=e.get('semantic_hints') or {}
 return (2 if any(r in h for r in wanted) else 0)+(1 if e.get('in_modal') else 0)+max([v for k,v in h.items() if k not in BAD],default=0)*.1
def compact(obs,state=None,limit=None):
 raw=[e for e in obs.get('elements',[]) if not any(k in (e.get('semantic_hints') or {}) for k in BAD)]
 wanted=ROLE_FOR_STATE.get(state or '',())
 modal=bool(obs.get('dialogs'))
 chosen=sorted([e for e in raw if (e.get('in_modal') or not modal) and not e.get('disabled')],key=lambda e:_strength(e,wanted),reverse=True)[:limit or MAX_EL]
 chosen.sort(key=lambda e:e['id'])
 els=[]
 for e in chosen:
  d={k:_clip(e.get(k),70) for k in KEEP if e.get(k) not in ('',None,False,{},[])}
  if d.get('semantic_hints'):d['semantic_hints']={k:v for k,v in d['semantic_hints'].items() if k not in BAD}
  els.append(d)
 return {'url':obs.get('url'),'title':_clip(obs.get('title'),80),'dialogs':[_clip(d,220) for d in obs.get('dialogs',[])[:3]],'elements':els,'text':_clip(obs.get('text',''),350)}
def _extract_json(raw):
 raw=(raw or '').strip()
 if not raw:raise ValueError('respuesta vacía')
 raw=re.sub(r'^```(?:json)?\s*|\s*```$','',raw,flags=re.I|re.S).strip()
 try:return json.loads(raw)
 except json.JSONDecodeError:pass
 m=re.search(r'\{.*\}',raw,re.S)
 if m:return json.loads(m.group(0))
 raise ValueError('no contiene JSON object parseable')
def _call(messages,timeout=240):
 payload={'model':MODEL,'stream':False,'think':False,'messages':messages,'options':{'temperature':0.0,'num_predict':160,'num_ctx':NUM_CTX},'keep_alive':'5m'}
 r=requests.post(HOST+'/api/chat',json=payload,timeout=timeout)
 if not r.ok:raise RuntimeError(f'Ollama HTTP {r.status_code}: {r.text[:800]}')
 j=r.json();msg=j.get('message') or {};content=msg.get('content','');thinking=msg.get('thinking','')
 if not content and thinking:raise ValueError(f'Ollama devolvió sólo thinking ({len(thinking)} chars)')
 return content,j
def build_messages(goal,observation,history,state=None,limit=None):
 body={'goal':{k:goal.get(k) for k in ('origin','destination','departure','return_date','cabin') if k in goal}|{'adults':len([a for a in goal.get('ages',[30]) if a>=18])},'harness':{'state':state or (observation.get('harness') or {}).get('state'),'guidance':(observation.get('harness') or {}).get('guidance','')},'observation':compact(observation,state or (observation.get('harness') or {}).get('state'),limit),'recent_actions':history[-4:]}
 st=body['harness']['state']
 return [{'role':'system','content':SYSTEM+'\n\n'+instructions(st)},{'role':'user','content':json.dumps(body,ensure_ascii=False,separators=(',',':'))}]
def plan(goal,observation,history,state=None):
 msgs=build_messages(goal,observation,history,state)
 try:raw,_=_call(msgs,240)
 except RuntimeError:
  msgs=build_messages(goal,observation,history,state,limit=18);msgs[0]['content']=SYSTEM;raw,_=_call(msgs,240)
 try:return _extract_json(raw)
 except Exception as first:
  repair=[{'role':'system','content':'Convert the answer into ONE valid JSON action object. No explanation, no markdown.'},{'role':'user','content':raw or '{"action":"wait","ms":1000}'}]
  raw2,_=_call(repair,120)
  try:return _extract_json(raw2)
  except Exception as second:raise ValueError(f'LLM sin JSON. primera={first}; raw1={raw[:300]!r}; segunda={second}; raw2={raw2[:300]!r}')
