import threading
from datetime import datetime
from .providers import AlmundoProvider,AerolineasProvider
from . import database,learning_store
class Agent:
 def __init__(self,status,log,obs):self.status=status;self.log=log;self.obs=obs;self.stop_event=threading.Event();self.thread=None;self.failures={};self.providers=[AlmundoProvider(),AerolineasProvider()]
 @property
 def running(self):return bool(self.thread and self.thread.is_alive())
 def start(self,r,minutes):
  if self.running:return
  self.stop_event.clear();self.thread=threading.Thread(target=self.run,args=(r,minutes),daemon=True);self.thread.start()
 def stop(self):self.stop_event.set();self.status('DETENIENDO')
 def run(self,r,m):
  self.status('EJECUTANDO');self.log(datetime.now(),'Agente iniciado con providers: '+', '.join(x.name for x in self.providers))
  while not self.stop_event.is_set():
   all_obs=[]
   for provider in self.providers:
    if self.stop_event.is_set():break
    try:
     suffix=' [EXPERIMENTAL]' if getattr(provider,'experimental',False) else ''
     self.log(datetime.now(),f'Consultando {provider.name}{suffix} {r.origin}->{r.destination}');o=provider.search(r);[database.insert(x) for x in o];all_obs.extend(o);self.log(datetime.now(),f'{provider.name}: {len(o)} oferta(s) verificable(s) guardada(s)')
     self.failures[provider.name]=0 if o else self.failures.get(provider.name,0)+1
     if self.failures[provider.name]>=3:
      goal={'origin':r.origin,'destination':r.destination,'departure':r.departure.isoformat(),'return_date':r.return_date.isoformat(),'ages':list(r.ages),'cabin':r.cabin,'required_currency':'USD'}
      url='https://www.aerolineas.com.ar/' if provider.name=='aerolineas' else 'https://almundo.com.ar/'
      learning_store.enqueue_repair_if_missing(provider.name,url,goal,f'{self.failures[provider.name]} ciclos sin observación verificable')
      self.log(datetime.now(),f'{provider.name}: reparación automática pendiente/encolada')
     if provider.name=='aerolineas':self.log(datetime.now(),'Aerolíneas estado: '+getattr(provider,'last_status','N/D'))
     if not o and provider.name=='aerolineas':self.log(datetime.now(),'Aerolíneas: revisar data/diagnostics. Cero resultados no se interpreta como precio inexistente.')
    except Exception as e:self.log(datetime.now(),f'ERROR {provider.name} {type(e).__name__}: {e}')
   self.obs(all_obs);self.status('ESPERANDO')
   if self.stop_event.wait(m*60):break
   self.status('EJECUTANDO')
  self.status('DETENIDO');self.log(datetime.now(),'Agente detenido')
