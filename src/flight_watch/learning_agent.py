"""Bucle de aprendizaje: Python decide el estado y ejecuta lo determinista; el LLM sólo desambigua.
No depende de SQLite ni de Ollama: recibe `planner` y `chat` inyectables (testeable con fakes)."""
from __future__ import annotations
import json,re,time
from collections import Counter
from pathlib import Path
from . import form_mapper,procedure
from .flight_harness import STATES,OPTIONAL,enrich,results_check
from .browser_learning import ALLOWED
from .navigation_guard import LoopGuard,blocked_click,blocked_page,off_task
from .semantic_forms import form_summary,role_state
from .validators import FLEX_URL
FLEX_RE=re.compile(r'flex',re.I)
MAX_ATTEMPTS={'LOCATE_FORM':8,'SET_TRIP_TYPE':3,'SET_ORIGIN':5,'SET_DESTINATION':5,'SET_DEPARTURE':5,'SET_RETURN':5,'SET_PASSENGERS':6,'SET_CABIN':4,'SET_CURRENCY':3,'SUBMIT':4,'VALIDATE_RESULTS':14,'EXTRACT_TOTAL':14}
ROLE_FOR={'SET_ORIGIN':'origin','SET_DESTINATION':'destination','SET_DEPARTURE':'departure_date','SET_RETURN':'return_date'}
CONFIRM_ROLE={'SET_ORIGIN':'origin','SET_DESTINATION':'destination','SET_DEPARTURE':'departure_date','SET_RETURN':'return_date'}
def stable_key(e):
 """Clave estable de un control entre observaciones (sin ids dinámicos ni data-fw-id)."""
 eid='' if procedure.DYNAMIC_ID.search(e.get('id_attr') or '') else e.get('id_attr','')
 return '|'.join(str(e.get(k) or '') for k in ('tag','type','name','placeholder','aria_label'))+'|'+eid+'|'+(e.get('class_attr') or '')
def apply_learned(obs,learned):
 """Reaplica a la observación los roles que el mapper LLM descubrió, para que determine_state los vea."""
 if not learned:return obs
 for e in obs['elements']:
  for role,key in learned.items():
   if stable_key(e)==key:e.setdefault('semantic_hints',{})[role]=max(e['semantic_hints'].get(role,0),.8)
 obs['role_state']=role_state(obs['elements']);obs['form_summary']=form_summary(obs['elements']);return obs
def elem(obs,i):return next((e for e in obs.get('elements',[]) if e['id']==i),None)
def ekey(e):return (e.get('id_attr') or e.get('name') or e.get('aria_label') or e.get('placeholder') or (e.get('text') or '')[:20] or e.get('tag') or '?') if e else '?'
class Recorder:
 """Guarda cada paso (observación + acción + resultado) para iterar offline sin el sitio real."""
 def __init__(self,dir_,html=True):
  self.dir=Path(dir_) if dir_ else None;self.html=html;self.n=0
  if self.dir:self.dir.mkdir(parents=True,exist_ok=True)
 def step(self,b,obs,state,action=None,result=None):
  if not self.dir:return
  self.n+=1;base=self.dir/f'step_{self.n:02d}'
  o={k:v for k,v in obs.items() if k not in ('full_text',)};o['full_text_len']=len(obs.get('full_text',''))
  base.with_suffix('.json').write_text(json.dumps({'state':state,'action':action,'result':result,'observation':o},ensure_ascii=False,indent=1,default=str),encoding='utf-8')
  if self.html:
   try:base.with_suffix('.html').write_text(b.snapshot_html(),encoding='utf-8')
   except Exception:pass
def sanitize(action,obs,state,goal):
 """Valida/normaliza una acción propuesta por el LLM. Lanza ValueError con el motivo si debe rechazarse."""
 if isinstance(action,dict) and not action.get('action'):
  alt=action.get('action_type') or action.get('type') or action.get('name')  # el modelo a veces usa otra clave
  args=action.get('arguments') if isinstance(action.get('arguments'),dict) else {}
  if alt in ALLOWED:action={**action,**args,'action':alt}
 if not isinstance(action,dict) or not action.get('action'):raise ValueError('acción sin campo action')
 a=dict(action);k=a['action']
 if k=='finish':raise ValueError('finish lo decide Python (validadores), no el LLM')
 if k=='fail':return a
 if k in ('back','restart','wait'):return a
 t=a.get('target_id')
 if isinstance(t,str) and t.strip().isdigit():t=a['target_id']=int(t)
 e=elem(obs,t) if isinstance(t,int) else None
 if e is None:raise ValueError(f'target_id {t!r} no existe en la observación actual')
 if k in ('click','press') and blocked_click(state,e)[0]:raise ValueError(f'control bloqueado ({blocked_click(state,e)[1]}); no es booking')
 if state=='LOCATE_FORM' and k in ('fill_airport','fill_date'):raise ValueError('en LOCATE_FORM primero hay que localizar el formulario')
 if state in ('SET_ORIGIN','SET_DESTINATION'):
  if k in ('fill','press'):raise ValueError('usá fill_airport para aeropuertos')
  if k=='fill_airport':
   h=e.get('semantic_hints') or {};other='destination' if state=='SET_ORIGIN' else 'origin';mine='origin' if state=='SET_ORIGIN' else 'destination'
   if other in h and mine not in h:raise ValueError(f'el control elegido es de {other}')
   a['iata']=goal['origin'] if state=='SET_ORIGIN' else goal['destination'];a['role']=mine
 if state in ('SET_DEPARTURE','SET_RETURN') and k in ('fill','fill_date'):
  a['action']='fill_date';a['iso']=str(goal['departure'] if state=='SET_DEPARTURE' else goal['return_date'])[:10];a['role']='departure' if state=='SET_DEPARTURE' else 'return'
 return a
def auto_action(state,obs,goal,mapping,tried,exclude=()):
 """Acción determinista para estados donde el mapeo es confiable; None delega al LLM."""
 def pick(role):
  m=mapping.get(role)
  if not m:return None
  for i in [m['id']]+list(m.get('alternatives',[])):
   e=elem(obs,i)
   if e and i not in exclude and tried[(state,ekey(e))]<2 and not blocked_click(state,e)[0]:return e
  return None
 if state=='LOCATE_FORM':
  e=pick('booking_entry');return {'action':'click','target_id':e['id'],'reason':'auto: entrada a booking'} if e else None
 if state=='SET_TRIP_TYPE':
  e=pick('trip_round');return {'action':'click','target_id':e['id'],'reason':'auto: ida y vuelta'} if e else None
 if state in ('SET_ORIGIN','SET_DESTINATION'):
  e=pick(ROLE_FOR[state])
  if e:return {'action':'fill_airport','target_id':e['id'],'iata':goal['origin'] if state=='SET_ORIGIN' else goal['destination'],'role':ROLE_FOR[state],'reason':'auto'}
  return None
 if state in ('SET_DEPARTURE','SET_RETURN'):
  e=pick(ROLE_FOR[state])
  if e:return {'action':'fill_date','target_id':e['id'],'iso':str(goal['departure'] if state=='SET_DEPARTURE' else goal['return_date'])[:10],'role':ROLE_FOR[state],'reason':'auto'}
  return None
 if state=='SUBMIT':
  for e in obs.get('elements',[]):  # "fechas flexibles" marcado por defecto lleva a un calendario de precios "desde", no a la fecha pedida
   if e.get('type')=='checkbox' and e.get('checked') and not e.get('disabled') and FLEX_RE.search(' '.join(str(e.get(k) or '') for k in ('name','label','aria_label','text','nearby_text'))) and tried[(state,ekey(e))]<2:return {'action':'uncheck','target_id':e['id'],'reason':'auto: desmarcar fechas flexibles'}
  e=pick('flight_search');return {'action':'click','target_id':e['id'],'reason':'auto: buscar vuelos'} if e else None
 if state in ('VALIDATE_RESULTS','EXTRACT_TOTAL'):
  if FLEX_URL.search(obs.get('url') or ''):return {'action':'fail','reason':'el sitio abrió el calendario de fechas flexibles en vez de los resultados de la fecha pedida'}
  return {'action':'wait','ms':2000,'reason':'auto: esperando resultados'}
 if state in ('SET_PASSENGERS','SET_CABIN'):
  want='adults' if state=='SET_PASSENGERS' else 'cabin'
  for e in obs.get('elements',[]):
   if e.get('tag')=='select' and want in (e.get('semantic_hints') or {}) and e.get('options') and tried[(state,ekey(e))]<2:
    n=len([a for a in goal.get('ages',[30]) if a>=18]) or 1;pat=re.compile(rf'(?<!\d){n}(?!\d)') if want=='adults' else re.compile(str(goal.get('cabin','ECONOMY')).replace('_',' '),re.I)
    opt=next((o for o in e['options'] if pat.search(o)),None)
    if opt:return {'action':'select','target_id':e['id'],'value':opt,'reason':'auto: select '+want}
  # combobox propio (botón + <li role=option>): con la lista desplegada se elige la opción ("2 Passengers"); no es un <select>
  n=len([a for a in goal.get('ages',[30]) if a>=18]) or 1
  pat=re.compile(rf'^\s*{n}\s*(adults?|passengers?|travell?ers?|pasajeros?|adultos?|viajeros?)\b',re.I) if want=='adults' else re.compile(str(goal.get('cabin','ECONOMY')).replace('_',' '),re.I)
  for c in obs.get('elements',[]):
   if c.get('expanded')=='true' and (want in (c.get('semantic_hints') or {} ) or (want=='adults' and 'passengers' in (c.get('semantic_hints') or {}))):
    for o in obs.get('elements',[]):
     if (o.get('role')=='option' or o.get('tag')=='li') and pat.search(o.get('text') or o.get('aria_label') or '') and tried[(state,ekey(o))]<2 and not o.get('disabled'):return {'action':'click','target_id':o['id'],'reason':'auto: opción de la lista'}
 if state=='SET_PASSENGERS':
  n=len([a for a in goal.get('ages',[30]) if a>=18]) or 1;plus=re.compile(r'(\badd\b|increase|plus|m[aá]s|agregar|aumentar|\+)',re.I)
  for e in obs.get('elements',[]):
   h=e.get('semantic_hints') or {};blob=' '.join(str(e.get(k) or '') for k in ('aria_label','text','class_attr','name'))
   if 'adults' in h and not e.get('disabled') and plus.search(blob) and not re.search(r'remove|decrease|menos|quitar|minus|sub',blob,re.I) and tried[(state,ekey(e))]<n+1:return {'action':'click','target_id':e['id'],'reason':'auto: sumar adulto'}
  for e in obs.get('elements',[]):
   h=e.get('semantic_hints') or {}
   if ('passengers' in h or 'cabin' in h) and e.get('tag')=='button' and e.get('expanded')!='true' and tried[(state,ekey(e))]<2 and not blocked_click(state,e)[0]:return {'action':'click','target_id':e['id'],'reason':'auto: abrir pasajeros'}
  return None
 if state=='SET_CURRENCY':
  for e in obs.get('elements',[]):
   if 'currency' in (e.get('semantic_hints') or {}) and not e.get('checked') and not e.get('disabled') and tried[(state,ekey(e))]<1 and (e.get('type') in ('checkbox','radio') or e.get('role') in ('switch','checkbox','radio')):return {'action':'check','target_id':e['id'],'reason':'auto: moneda USD'}
 return None
def run_learning(b,goal,planner,emit,chat=None,max_steps=40,cancelled=lambda:False,recorder=None,llm_map_budget=3,provider='provider',on_step=None):
 """Devuelve {'status','reason','procedure','validation','steps','llm_calls'}. status: COMPLETED|FAILED|CANCELLED_BY_USER."""
 start=b.start_url;proc=procedure.new_procedure(provider,start,goal);rec=recorder or Recorder(None)
 history=[];guard=LoopGuard();attempts=Counter();tried=Counter();skipped=set();confirmed=set();stats=Counter();offtask_backs=0;restarts=0
 prev=None;last_idx=-1;last_sig=None;last_url=None;last_conf=0;res_waits=0;learned={}
 clicked=b.dismiss_banners()
 if clicked:emit('INFO',f'banners resueltos por Python: {clicked}')
 def finish(status,reason,validation=None):
  proc['status']='candidate' if status=='COMPLETED' else 'failed';proc['validation']=validation
  return {'status':status,'reason':reason,'procedure':proc,'validation':validation,'steps':len(proc['steps']),'llm_calls':stats['llm'],'llm_mapper_calls':stats['llm_map']}
 for step in range(1,max_steps+1):
  if cancelled():return finish('CANCELLED_BY_USER','cancelado por usuario')
  obs=b.observe()
  if blocked_page(obs):
   msg=f"el sitio bloqueó la sesión (acceso denegado/captcha) en {obs['url'][:90]} tras {len(proc['steps'])} pasos válidos; no se reintenta ni se intenta evadir"
   proc['notes'].append(msg);rec.step(b,obs,'BLOCKED',None,'blocked');emit('ERROR',msg);return finish('FAILED','bloqueado por el sitio: '+(obs.get('text') or '')[:120].replace('\n',' '))
  if not obs.get('elements'):
   emit('WARN','Sin elementos interactivos; reobservando');b.page.wait_for_timeout(1200)
   if step>=max_steps-1:return finish('FAILED','sin elementos interactivos')
   continue
  obs=enrich(apply_learned(obs,learned),goal,skipped,start,confirmed);state=obs['harness']['state'];idx=STATES.index(state);sig=b.signature(obs)
  if on_step:on_step(step,state)
  changed=(sig!=last_sig) if last_sig else True;progressed=idx>last_idx or obs['url']!=last_url or len(confirmed)>last_conf
  if prev is not None and prev.get('action')!='wait':guard.record(prev,changed,progressed)
  last_idx=max(last_idx,idx) if state not in ('LOCATE_FORM',) else last_idx;last_sig=sig;last_url=obs['url'];last_conf=len(confirmed)
  emit('HARNESS',f"paso {step}: state={state} · {obs['title'][:50]!r} · {len(obs['elements'])} elementos · {obs['url'][:90]}")
  if state=='COMPLETE':
   v=results_check(obs,goal,start)
   if v.get('native_usd') and not any(x['state']=='SET_CURRENCY' for x in proc['steps']):  # el perfil persistente ya tenía USD activo: sin este paso un perfil limpio mostraría otra moneda
    for ce in obs.get('elements',[]):
     if 'currency' in (ce.get('semantic_hints') or {}) and ce.get('type') in ('checkbox','radio') and ce.get('checked'):
      cl=procedure.unique_locators(b._frames.get(ce['id']) or b.page,procedure.locators_for(ce))
      if cl:proc['steps'].append(procedure.make_step('SET_CURRENCY',{'action':'check'},ce,ce.get('frame',0),cl));proc['notes'].append('paso SET_CURRENCY añadido: el switch USD ya estaba activo en el perfil de aprendizaje')
      break
   proc['price_basis']=v.get('price_basis');proc['result_url']=obs['url'];rec.step(b,obs,state,None,'COMPLETE')
   if v.get('price_basis')=='unknown':proc['notes'].append('Base del precio no verificada (total vs por pasajero): revisar antes de promover.')
   if v.get('note'):proc['notes'].append(v['note'])
   emit('INFO',f"Resultados validados: {v['price_candidate']} · basis={v.get('price_basis')} · {v.get('note','')}");return finish('COMPLETED','resultados validados',v)
  off,why=off_task(obs['url'])
  if off:
   proc['notes'].append(f'off_task {why} en {obs["url"][:80]}');emit('WARN',f'Fuera de tarea ({why}); ')
   if offtask_backs<2:offtask_backs+=1;act={'action':'back'}
   else:act={'action':'restart'}
  else:
   act=None
   verdict=guard.verdict(sig)
   if verdict!='ok':emit('WARN',f'LoopGuard={verdict} (visitas={guard.visits[sig]}, sin progreso={guard.no_progress})');act={'action':'back' if verdict=='back' else 'restart'}
  if act is None:
   attempts[state]+=1
   if attempts[state]>MAX_ATTEMPTS.get(state,6):
    if state in OPTIONAL:skipped.add(state);proc['notes'].append(f'{state} omitido tras {attempts[state]-1} intentos');emit('WARN',f'{state} opcional omitido');attempts[state]=0;prev=None;continue
    v=results_check(obs,goal,start)
    return finish('FAILED',f'estado {state} sin progreso tras {attempts[state]-1} intentos',v)
   mapping=form_mapper.heuristic_map(obs)
   if state=='LOCATE_FORM' and chat and not learned and stats['llm_map']<llm_map_budget and form_mapper.worth_asking(obs):
    stats['llm_map']+=1;mapping=form_mapper.map_form(obs,chat)
    for r_,m_ in mapping.items():
     if m_.get('via')=='llm' and elem(obs,m_['id']):learned[r_]=stable_key(elem(obs,m_['id']))
    emit('INFO',f'mapper LLM en LOCATE_FORM: {sorted(learned)}')
    if learned:continue
   role=ROLE_FOR.get(state)
   need_llm=role and (role not in mapping or mapping[role]['ambiguous']) and chat and stats['llm_map']<llm_map_budget and form_mapper.worth_asking(obs)
   if need_llm:
    stats['llm_map']+=1;mapping=form_mapper.map_form(obs,chat)
    for r_,m_ in mapping.items():
     if m_.get('via')=='llm' and elem(obs,m_['id']):learned[r_]=stable_key(elem(obs,m_['id']))
    emit('INFO',f'mapper LLM ({stats["llm_map"]}): {({k:v["id"] for k,v in mapping.items()})}')
   exclude=()
   if state=='SET_DESTINATION' and 'origin' in mapping:exclude=(mapping['origin']['id'],)
   act=auto_action(state,obs,goal,mapping,tried,exclude);source='auto'
   if act is None:
    t=time.monotonic();stats['llm']+=1
    try:raw=planner(goal,obs,history,state)
    except Exception as e:
     emit('ERROR',f'planner: {type(e).__name__}: {str(e)[:300]}');history.append({'executor_error':str(e)[:120]});prev=None
     if stats['llm']>=3 and stats['llm']>=step-1 and not proc['steps']:return finish('FAILED',f'planner no disponible: {e}')
     continue
    emit('INFO',f'LLM respondió en {time.monotonic()-t:.1f}s');emit('ACTION',json.dumps(raw,ensure_ascii=False))
    try:act=sanitize(raw,obs,state,goal)
    except ValueError as e:
     emit('WARN',f'Acción rechazada: {e}');history.append({'executor_error':str(e)});prev=None;continue
    source='llm'
   else:emit('ACTION',json.dumps(act,ensure_ascii=False)+' [auto]')
   if act['action']=='fail':
    v=results_check(obs,goal,start);return finish('FAILED',str(act.get('reason') or 'fail del planner'),v)
   if guard.repeated(act) and act['action'] not in ('wait',):
    emit('WARN','Acción repetida sin efecto; rechazada');history.append({'executor_error':'repeated action'});tried[(state,ekey(elem(obs,act.get('target_id'))))]+=2;prev=None;continue
  # ---- ejecución
  e=elem(obs,act.get('target_id')) if isinstance(act.get('target_id'),int) else None;locs=None
  if e and act['action'] not in ('back','restart','wait'):
   fr=b._frames.get(e['id']) or b.page;locs=procedure.unique_locators(fr,procedure.locators_for(e))
  try:result=b.act(act)
  except Exception as ex:
   msg=f'{type(ex).__name__}: {str(ex)[:240]}'
   emit('WARN',f'Acción rechazada: {msg}');history.append({'executor_error':msg})
   if e:tried[(state,ekey(e))]+=1
   rec.step(b,obs,state,act,{'error':msg});prev=None;continue
  b.page.wait_for_timeout(500);prev=act
  if act['action']=='wait' and state in ('VALIDATE_RESULTS','EXTRACT_TOTAL'):res_waits+=1
  history.append({k:act.get(k) for k in ('action','target_id','iata','iso','value','role') if act.get(k) is not None})
  rec.step(b,obs,state,act,result if isinstance(result,dict) else 'ok')
  if act['action']=='restart':
   restarts+=1;proc['steps']=[];confirmed.clear();guard.reset();last_idx=-1;last_sig=None
   if restarts>3:return finish('FAILED','demasiados reinicios')
   continue
  if act['action']=='back':
   if proc['steps']:proc['steps'].pop()
   continue
  if act['action']=='wait':continue
  if e:
   tried[(state,ekey(e))]+=1
   if act['action'] in ('fill_airport','fill_date') and isinstance(result,dict) and result.get('confirmed'):confirmed.add(CONFIRM_ROLE.get(state,''))
   if locs:
    s=procedure.make_step(state,act,e,e.get('frame',0),locs)
    if act['action'] in ('fill_airport','fill_date'):proc['steps']=[x for x in proc['steps'] if x['state']!=state]
    proc['steps'].append(s)
   else:proc['notes'].append(f'paso {state} sin locator único; no reproducible')
 v=results_check(b.observe(),goal,start)
 return finish('FAILED',f'máximo de {max_steps} pasos alcanzado',v)
