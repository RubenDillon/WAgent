"""Procedimiento aprendido: serializable, versionado y reejecutable por Python sin LLM."""
from __future__ import annotations
import json,re,time
from datetime import datetime
from pathlib import Path
BASE=Path(__file__).resolve().parents[2]
PROC_DIR=BASE/'data'/'procedures'
SCHEMA=1
UNSTABLE_CLASS=re.compile(r'^(sc-|css-|jsx-|_|styled|emotion|mui)|\d{3,}')
STABLE_CLASS=re.compile(r'^[a-z][a-z0-9]*(?:[-_]{1,2}[a-z0-9]+)+$')
DYNAMIC_ID=re.compile(r'[0-9a-f]{8}-[0-9a-f]{4}|\d{5,}|^:r|^(react|rc|mui)-?[\w-]*\d')
PARAM_FOR_STATE={'SET_ORIGIN':'origin','SET_DESTINATION':'destination','SET_DEPARTURE':'departure','SET_RETURN':'return_date'}
def _q(v):return str(v).replace('\\','\\\\').replace('"','\\"')
def locators_for(e):
 """Estrategias de localización ordenadas de más a menos estable para un elemento observado."""
 tag=e.get('tag') or '*';out=[]
 eid=e.get('id_attr') or ''
 if eid and not DYNAMIC_ID.search(eid):out.append({'kind':'css','value':f'[id="{_q(eid)}"]'})
 if e.get('name'):out.append({'kind':'css','value':f'{tag}[name="{_q(e["name"])}"]'})
 if e.get('data_attrs'):
  try:
   for k,v in (json.loads(e['data_attrs']) or {}).items():
    if k in ('data-testid','data-test','data-qa','data-cy','data-test-id','data-automation-id') and v:out.append({'kind':'css','value':f'{tag}[{k}="{_q(v)}"]'})
  except Exception:pass
 if e.get('aria_label'):out.append({'kind':'css','value':f'{tag}[aria-label="{_q(e["aria_label"])}"]'})
 if e.get('placeholder') and tag in ('input','textarea'):out.append({'kind':'css','value':f'{tag}[placeholder="{_q(e["placeholder"])}"]'})
 classes=[c for c in (e.get('class_attr') or '').split() if STABLE_CLASS.match(c) and not UNSTABLE_CLASS.search(c)]
 if classes:out.append({'kind':'css','value':tag+''.join('.'+c for c in classes[:3])})
 t=re.sub(r'\s+',' ',e.get('text') or e.get('label') or '').strip()
 if t and len(t)<=40 and (tag in ('button','a','label','li') or e.get('role') in ('button','tab','option','switch','radio')):out.append({'kind':'text','tag':tag,'value':t[:40]})
 seen=set();uniq=[]
 for l in out:
  k=json.dumps(l,sort_keys=True)
  if k not in seen:seen.add(k);uniq.append(l)
 return uniq
def resolve(frame,loc):
 if loc['kind']=='css':return frame.locator(loc['value'])
 if loc['kind']=='text':return frame.locator(loc.get('tag') or '*').filter(has_text=re.compile(r'^\s*'+re.escape(loc['value'])+r'\s*$'))
 raise ValueError(f'locator desconocido: {loc}')
def unique_locators(frame,locs):
 """Conserva los locators que hoy resuelven exactamente un elemento (los demás son ambiguos)."""
 keep=[]
 for l in locs:
  try:
   if resolve(frame,l).count()==1:keep.append(l)
  except Exception:pass
 return keep
def new_procedure(provider,start_url,goal):
 return {'schema':SCHEMA,'provider':provider,'start_url':start_url,'created_at':datetime.now().isoformat(timespec='seconds'),'goal_example':goal,'steps':[],'status':'draft','notes':[]}
def make_step(state,action,element,frame_index,unique):
 """Paso reproducible. Los valores del objetivo se guardan como parámetros, no como literales."""
 a={'state':state,'action':action['action'],'frame':frame_index,'locators':unique,'label':(element.get('text') or element.get('aria_label') or element.get('placeholder') or element.get('id_attr') or '')[:60]}
 param=PARAM_FOR_STATE.get(state)
 if action['action'] in ('fill_airport','fill_date') and param:a['param']=param
 elif action['action'] in ('fill','select'):a['value']=action.get('value')
 elif action['action']=='press':a['key']=action.get('key','Enter')
 if action['action']=='fill_airport':a['role']='origin' if state=='SET_ORIGIN' else 'destination'
 if action['action']=='fill_date':a['role']='departure' if state=='SET_DEPARTURE' else 'return'
 return a
def save(proc,dir_=None):
 d=Path(dir_) if dir_ else PROC_DIR/re.sub(r'[^a-z0-9_]+','_',proc['provider'].lower());d.mkdir(parents=True,exist_ok=True)
 existing=sorted(int(m.group(1)) for p in d.glob('v*.json') if (m:=re.match(r'v(\d+)\.json$',p.name)))
 v=(existing[-1]+1) if existing else 1;proc['version']=v;p=d/f'v{v}.json'
 p.write_text(json.dumps(proc,ensure_ascii=False,indent=1),encoding='utf-8');return p
def load(path):return json.loads(Path(path).read_text(encoding='utf-8'))
def latest(provider,dir_=None):
 d=Path(dir_) if dir_ else PROC_DIR/re.sub(r'[^a-z0-9_]+','_',provider.lower())
 files=sorted(d.glob('v*.json'),key=lambda p:int(re.match(r'v(\d+)',p.name).group(1))) if d.exists() else []
 return load(files[-1]) if files else None
class ProcedureError(Exception):
 def __init__(self,index,message):super().__init__(f'paso {index}: {message}');self.index=index
def _param(step,goal):
 p=step.get('param')
 if p=='origin':return {'iata':goal['origin']}
 if p=='destination':return {'iata':goal['destination']}
 if p=='departure':return {'iso':str(goal['departure'])[:10]}
 if p=='return_date':return {'iso':str(goal['return_date'])[:10]}
 return {}
def run_procedure(b,proc,goal,on_event=None,result_timeout=30,poll=1.5):
 """Reejecuta un procedimiento sin LLM. Devuelve {'ok','validation','steps_done'} o lanza ProcedureError."""
 from .validators import validate_results
 ev=on_event or (lambda lvl,msg:None)
 frames=b._frames_to_scan();clicked=b.dismiss_banners()
 if clicked:ev('INFO',f'banners resueltos: {clicked}')
 done=0
 for i,s in enumerate(proc['steps']):
  b.page.wait_for_timeout(250);frames=b._frames_to_scan();fr=frames[min(s.get('frame',0),len(frames)-1)];found=None
  deadline=time.monotonic()+(15 if i==0 else 8);tries=0  # SPAs (React) renderizan tarde: se sondea hasta el plazo, no sólo 2 veces
  while not found:
   for l in s['locators']:
    try:
     q=resolve(fr,l)
     if not q.count():continue
     q.first.wait_for(state='attached' if s['action'] in ('check','uncheck') else 'visible',timeout=1500);found=(q.first,l);break
    except Exception:continue
   if found or time.monotonic()>=deadline:break
   tries+=1
   if tries%3==1:b.dismiss_banners()
   b.page.wait_for_timeout(600);frames=b._frames_to_scan();fr=frames[min(s.get('frame',0),len(frames)-1)]
  if not found:raise ProcedureError(i,f'ningún locator resuelve ({s["label"]!r}): {[x.get("value") for x in s["locators"]]}')
  fr.evaluate("()=>document.querySelectorAll('[data-fw-id=\"9999\"]').forEach(e=>e.removeAttribute('data-fw-id'))");found[0].evaluate("e=>e.setAttribute('data-fw-id','9999')");b._frames[9999]=fr
  act={'action':s['action'],'target_id':9999,'value':s.get('value'),'key':s.get('key'),'role':s.get('role')};act.update(_param(s,goal))
  try:b.act(act)
  except Exception as e:raise ProcedureError(i,f'{s["action"]} falló: {str(e)[:200]}')
  done+=1;ev('INFO',f'procedimiento paso {i+1}/{len(proc["steps"])}: {s["action"]} {s["label"]!r} via {found[1].get("kind")}')
 best=None;t0=time.monotonic()
 while time.monotonic()-t0<result_timeout:
  b.page.wait_for_timeout(int(poll*1000));v=validate_results(b.page.url,b.page_text(60000),goal);best=v
  if v['ok'] and not (v['currency']!='USD' and v['native_usd_option'] and any(x['state']=='SET_CURRENCY' for x in proc['steps']) and time.monotonic()-t0<result_timeout-5):break  # tras activar USD, espera a que la página recalcule
 return {'ok':bool(best and best['ok']),'validation':best,'steps_done':done,'url':b.page.url}
