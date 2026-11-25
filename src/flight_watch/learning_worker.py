from __future__ import annotations
import json,os,signal,time,traceback
from datetime import datetime
from pathlib import Path
from . import learning_store as store,procedure
from .browser_learning import LearningBrowser
from .learning_agent import run_learning,Recorder
from .ollama_lifecycle import OllamaLifecycle
from .ollama_planner import plan,set_model,_call
VERSION='0.14.0'
DIAG=Path(__file__).resolve().parents[2]/'data'/'diagnostics'/'learning'
STOP=False
def stop(*_):
 global STOP;STOP=True
def event(jid,level,msg):store.add_event(jid,level,msg)
def chat(messages):return _call(messages,120)[0]
PRICE_TOLERANCE=0.25  # los precios de aerolíneas se mueven entre sesiones; una diferencia mayor indica que el procedimiento no reproduce lo aprendido
def compare_with_learned(learned,shadow):
 """Devuelve None si la reejecución coincide con lo aprendido (misma moneda, precio dentro de tolerancia) o el motivo de la discrepancia."""
 a=(learned or {}).get('price_candidate');b=(shadow or {}).get('price_candidate')
 if not a or not b:return None
 if a['currency']!=b['currency']:return f"la reejecución da {b['currency']} {b['amount']:g} pero se aprendió {a['currency']} {a['amount']:g}: falta fijar la moneda en el procedimiento"
 if a['amount'] and abs(b['amount']-a['amount'])/a['amount']>PRICE_TOLERANCE:return f"precio de la reejecución {b['amount']:g} difiere más de {PRICE_TOLERANCE:.0%} del aprendido {a['amount']:g}"
 return None
def shadow_validate(job,goal,proc,emit):
 """Reejecuta el procedimiento sin LLM en un perfil limpio. Un candidato sólo sirve si es reproducible."""
 try:
  with LearningBrowser(job['provider'],job['start_url'],ephemeral=True) as b:
   r=procedure.run_procedure(b,proc,goal,on_event=emit)
  mismatch=compare_with_learned(proc.get('validation'),r.get('validation')) if r['ok'] else None
  if mismatch:emit('WARN','Shadow validation: '+mismatch)
  return {'ok':r['ok'] and not mismatch,'validation':r.get('validation'),'url':r.get('url'),**({'error':mismatch} if mismatch else {})}
 except procedure.ProcedureError as e:return {'ok':False,'error':str(e),'step':e.index}
 except Exception as e:return {'ok':False,'error':f'{type(e).__name__}: {str(e)[:300]}'}
def execute(job):
 jid=job['id'];goal=json.loads(job['goal_json']);emit=lambda lvl,msg:event(jid,lvl,msg);max_steps=int(job.get('max_actions') or 40)
 try:
  rec=Recorder(DIAG/f'job_{jid}')
  with LearningBrowser(job['provider'],job['start_url']) as b:
   def on_step(n,state):store.update(jid,n,f'{state} · paso {n}/{max_steps}',{'state':state,'url':b.page.url})
   res=run_learning(b,goal,plan,emit,chat=chat,max_steps=max_steps,cancelled=lambda:STOP or store.cancellation_requested(jid),recorder=rec,provider=job['provider'],on_step=on_step)
  emit('INFO',f"Aprendizaje: {res['status']} · {res['reason']} · pasos={res['steps']} · llamadas LLM={res['llm_calls']} (mapper={res['llm_mapper_calls']})")
  if res['status']=='CANCELLED_BY_USER':store.finish(jid,'CANCELLED_BY_USER');emit('WARN','Cancelado por usuario');return
  if res['status']!='COMPLETED':store.finish(jid,'FAILED',res['reason']);return
  proc=res['procedure'];proc['learned_at']=datetime.now().isoformat(timespec='seconds');proc['job_id']=jid
  emit('INFO','Shadow validation: reejecutando el procedimiento sin LLM en un perfil limpio');sv=shadow_validate(job,goal,proc,emit);proc['shadow']=sv
  proc['status']='candidate' if sv['ok'] else 'candidate_unverified';path=procedure.save(proc)
  if sv['ok']:emit('INFO',f'Procedimiento candidato guardado y reproducible: {path}. NO se promueve a producción automáticamente.');store.finish(jid,'COMPLETED')
  else:emit('WARN',f"Procedimiento guardado pero no reproducible ({sv.get('error') or 'resultados no validados'}): {path}");store.finish(jid,'FAILED',f"shadow validation falló: {sv.get('error') or 'resultados no validados'}")
 except Exception as e:emit('ERROR',f'{type(e).__name__}: {e}');store.finish(jid,'FAILED',traceback.format_exc()[-4000:])
def main():
 signal.signal(signal.SIGTERM,stop);signal.signal(signal.SIGINT,stop);store.ensure();store.recover_interrupted();print(f'WORKER_START {VERSION}',flush=True);life=OllamaLifecycle();idle=None
 try:
  while not STOP:
   try:job=store.claim_next()
   except Exception as e:print(f'CLAIM_ERROR {type(e).__name__}: {e}',flush=True);time.sleep(2);continue
   if not job:
    if idle and time.time()-idle>=300:life.cooldown_shutdown();idle=None
    time.sleep(1);continue
   print(f"CLAIMED job={job['id']} provider={job['provider']}",flush=True)
   try:
    life.ensure(lambda m:event(job['id'],'OLLAMA',m));model=life.resolve_model(os.getenv('FLIGHT_WATCH_MODEL','granite4.2:8b'))
    if not model:raise RuntimeError('No hay modelo Ollama local')
    set_model(model);event(job['id'],'OLLAMA',f'Modelo seleccionado: {model}');execute(job)
   except Exception as e:event(job['id'],'ERROR',f'{type(e).__name__}: {e}');store.finish(job['id'],'FAILED',traceback.format_exc()[-4000:])
   idle=time.time()
 finally:life.cooldown_shutdown()
if __name__=='__main__':main()
