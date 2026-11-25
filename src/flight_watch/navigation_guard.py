from __future__ import annotations
import re
from collections import Counter
CONTENT_URL=re.compile(r'/(route-map|find-your-destination|travel-planning-center|destinations|explore|inspiration|offers-and-deals)(?:/|$|\?)',re.I)
SITE_SEARCH_URL=re.compile(r'/(site)?search(?:\?|/|$)',re.I)
BOOKING_URL=re.compile(r'(flight|booking|shop|availability|vuelos|offers|select)',re.I)
def off_task(url):
 u=url or ''
 if CONTENT_URL.search(u):return True,'content_navigation'
 if SITE_SEARCH_URL.search(u) and not BOOKING_URL.search(u):return True,'site_search'
 return False,''
def blocked_click(state,element):
 """Impide pulsar controles que ya sabemos que no son de booking. Se aplica en todos los estados, no sólo LOCATE_FORM."""
 if not element:return False,''
 h=element.get('semantic_hints') or {}
 if h.get('site_search',0)>=.7:return True,'site_search'
 if h.get('content_navigation',0)>=.7:return True,'content_navigation'
 return False,''
class LoopGuard:
 """Detecta repetición: misma firma de estado visitada demasiadas veces, o acciones idénticas / sin progreso consecutivas."""
 def __init__(self,max_visits=4,max_no_progress=3,max_same_action=2):
  self.visits=Counter();self.no_progress=0;self.last=[];self.max_visits=max_visits;self.max_no_progress=max_no_progress;self.max_same_action=max_same_action
 @staticmethod
 def key(action):return (action.get('action'),action.get('target_id'),str(action.get('value') or action.get('iata') or ''))
 def seen(self,signature):
  self.visits[signature]+=1;return self.visits[signature]
 def record(self,action,changed,progressed):
  self.last=(self.last+[self.key(action)])[-6:]
  self.no_progress=0 if (changed and progressed) else self.no_progress+1
 def repeated(self,action):return self.last[-self.max_same_action:].count(self.key(action))>=self.max_same_action
 def verdict(self,signature):
  """'ok' | 'back' | 'restart'. back ante estancamiento leve, restart si es persistente."""
  v=self.seen(signature)
  if self.no_progress>=self.max_no_progress*2 or v>self.max_visits+2:return 'restart'
  if self.no_progress>=self.max_no_progress or v>self.max_visits:return 'back'
  return 'ok'
 def reset(self):self.visits.clear();self.no_progress=0;self.last=[]
BLOCK_RE=re.compile(r"access denied|you don'?t have permission to access|request blocked|unusual traffic|are you a (human|robot)|verify you are (a )?human|captcha|acceso denegado|pardon our interruption|bot detected",re.I)
def blocked_page(obs):
 """¿El sitio rechazó la sesión (bot management / captcha)? Sólo con página casi vacía: así no se confunde con texto de marketing."""
 txt=(obs.get('full_text') or obs.get('text') or '')
 return bool(len(txt)<1500 and len(obs.get('elements') or [])<=6 and BLOCK_RE.search((obs.get('title') or '')+' '+txt))
