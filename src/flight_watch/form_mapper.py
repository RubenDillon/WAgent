"""Mapeo de formulario: asignación rol->control. Heurística primero; el LLM sólo desambigua y Python verifica."""
from __future__ import annotations
import json,re
from .navigation_guard import blocked_click
ROLES=('origin','destination','departure_date','return_date','flight_search','booking_entry','trip_round')
EDITABLE_ROLES=('origin','destination')
def _editable(e):return e.get('tag') in ('input','textarea') or e.get('role') in ('combobox','textbox') or bool(e.get('contenteditable'))
def _picker(role,e):
 """Botón que abre un selector (modal con buscador): origen/destino no siempre son <input> en la página."""
 return (e.get('tag')=='button' or e.get('role')=='button') and (e.get('semantic_hints') or {}).get(role,0)>=.9
def _compatible(role,e):
 """Restricciones duras por rol; el LLM no puede saltárselas."""
 if e.get('disabled'):return False
 if blocked_click('',e)[0]:return False
 if role in EDITABLE_ROLES:return _editable(e) or _picker(role,e)
 if role in ('departure_date','return_date'):return _editable(e) or e.get('tag') in ('button','div','span') or e.get('role') in ('combobox','button','textbox')
 if role=='flight_search':return e.get('tag') in ('button','a','input') or e.get('role')=='button'
 if role=='booking_entry':return e.get('tag') in ('button','a') or e.get('role') in ('tab','button')
 return True
def _score(role,e):
 h=e.get('semantic_hints') or {};s=h.get(role,0)
 if not s:return 0
 if e.get('offscreen'):s-=.05
 if e.get('in_modal'):s+=.02
 if role in EDITABLE_ROLES and _editable(e):s+=.05
 if role=='flight_search' and e.get('tag')=='button':s+=.03
 return s
def candidates(obs,role):
 out=[(e,_score(role,e)) for e in obs.get('elements',[]) if _compatible(role,e)]
 out=[x for x in out if x[1]>0];out.sort(key=lambda x:x[1],reverse=True);return out
def heuristic_map(obs):
 """{role:{'id':n,'score':s,'ambiguous':bool}} — ambiguous si el segundo candidato casi empata."""
 m={};used=set()
 for role in ROLES:
  cs=[c for c in candidates(obs,role) if c[0]['id'] not in used]
  if not cs:continue
  top=cs[0];amb=len(cs)>1 and cs[1][1]>=top[1]-.01 and role not in ('booking_entry','flight_search','trip_round')
  m[role]={'id':top[0]['id'],'score':round(top[1],2),'ambiguous':amb,'alternatives':[c[0]['id'] for c in cs[1:4]]}
  h_=top[0].get('semantic_hints') or {}
  if (role in EDITABLE_ROLES or role in ('departure_date','return_date')) and not ('departure_date' in h_ and 'return_date' in h_):used.add(top[0]['id'])
 return m
def verify(role,element_id,obs):
 e=next((x for x in obs.get('elements',[]) if x['id']==element_id),None)
 return bool(e) and _compatible(role,e)
LLM_SYSTEM='''Map flight-search form controls. Reply with ONE JSON object {"origin":id|null,"destination":id|null,"departure_date":id|null,"return_date":id|null,"flight_search":id|null}.
Use only ids from the candidate lists. origin/destination must be editable inputs and different from each other. Never choose site search or content links. Use null if unsure.'''
_KEYS=('id','tag','type','id_attr','name','placeholder','aria_label','label','text','value')
def llm_map(obs,roles,chat):
 """Una única llamada que sólo ve candidatos de los roles dudosos. `chat(messages)->str`."""
 cand={}
 for r in roles:
  cs=[e for e,_ in candidates(obs,r)[:6]]
  if not cs:cs=[e for e in obs.get('elements',[]) if _compatible(r,e) and not e.get('in_header')][:12]
  cand[r]=[{k:e.get(k) for k in _KEYS if e.get(k)} for e in cs]
 raw=chat([{'role':'system','content':LLM_SYSTEM},{'role':'user','content':json.dumps({'roles':list(roles),'candidates':cand},ensure_ascii=False,separators=(',',':'))}])
 m=re.search(r'\{.*\}',raw or '',re.S)
 if not m:return {}
 try:j=json.loads(m.group(0))
 except json.JSONDecodeError:return {}
 out={}
 for r in roles:
  v=j.get(r)
  if isinstance(v,int) and verify(r,v,obs):out[r]={'id':v,'score':.6,'ambiguous':False,'alternatives':[],'via':'llm'}
 ids=[x['id'] for k,x in out.items() if k in EDITABLE_ROLES]
 if len(ids)!=len(set(ids)):return {k:v for k,v in out.items() if k not in EDITABLE_ROLES}
 return out
def worth_asking(obs):
 """¿Vale la pena gastar una llamada LLM? Sólo si parece un formulario (varios inputs editables) o ya hay un submit de vuelos."""
 els=obs.get('elements',[]);ed=[e for e in els if _editable(e) and not e.get('in_header') and not blocked_click('',e)[0]]
 return len(ed)>=2 and ('flight_search' in obs.get('form_summary',{}).get('roles_found',{}) or obs.get('form_summary',{}).get('possible_flight_search_form',0)>=.2)
def map_form(obs,chat=None):
 """Heurística + (opcional) una llamada LLM para roles faltantes/ambiguos. Siempre verificado por Python."""
 m=heuristic_map(obs);doubtful=[r for r in ('origin','destination','departure_date','return_date') if r not in m or m[r]['ambiguous']]
 if doubtful and chat and worth_asking(obs):
  try:
   for r,v in llm_map(obs,doubtful,chat).items():m[r]=v
  except Exception:pass
 return m
