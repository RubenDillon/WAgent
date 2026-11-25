from __future__ import annotations
import re
from pathlib import Path
from urllib.parse import urlsplit
from .validators import date_matches,digits_token,validate_results
ROOT=Path(__file__).resolve().parents[2]/'agent_skills'/'flight-search-harness'
STATES=['LOCATE_FORM','SET_TRIP_TYPE','SET_ORIGIN','SET_DESTINATION','SET_DEPARTURE','SET_RETURN','SET_PASSENGERS','SET_CABIN','SET_CURRENCY','SUBMIT','VALIDATE_RESULTS','EXTRACT_TOTAL','COMPLETE']
OPTIONAL={'SET_TRIP_TYPE','SET_PASSENGERS','SET_CABIN','SET_CURRENCY'}
CABIN_WORDS={'ECONOMY':r'economy|turista|coach|main cabin|economica|económica','BUSINESS':r'business|ejecutiva|club','PREMIUM_ECONOMY':r'premium','FIRST':r'first|primera'}
STATE_REF={'LOCATE_FORM':['navigation-patterns.md'],'SET_ORIGIN':['form-semantics.md','navigation-patterns.md'],'SET_DESTINATION':['navigation-patterns.md'],'SET_DEPARTURE':['navigation-patterns.md'],'SET_RETURN':['navigation-patterns.md'],'SUBMIT':['aerolineas-lessons.md'],'VALIDATE_RESULTS':['validation-rules.md'],'EXTRACT_TOTAL':['validation-rules.md']}
def _read(rel):
 p=ROOT/rel
 return p.read_text(encoding='utf-8') if p.exists() else ''
def _body(md):
 """SKILL.md sin frontmatter."""
 return re.sub(r'^---.*?---\s*','',md,count=1,flags=re.S)
def instructions(state=None,limit=3000):
 """Instrucciones acotadas. Con `state` devuelve sólo el núcleo + la referencia relevante a ese estado (no los 6,5 KB completos)."""
 core=_body(_read('SKILL.md'))
 core=re.split(r'\n## State machine',core)[0].strip()
 if state is None:
  return '\n\n'.join([core]+[_read(f'references/{n}') for n in ('form-semantics.md','navigation-patterns.md','validation-rules.md','aerolineas-lessons.md')])[:14000]
 refs='\n\n'.join(_read('references/'+n) for n in STATE_REF.get(state,[]))
 return (core+'\n\n'+refs)[:limit]
def _vals(rs,role):return [str(x.get('value','')).strip() for x in rs.get(role,[])]
def _any_val(rs,role,pred):return any(pred(v) for v in _vals(rs,role) if v)
def _adults(goal):return len([x for x in goal.get('ages',[30]) if x>=18]) or 1
def _cabin_re(goal):return re.compile(CABIN_WORDS.get(str(goal.get('cabin','ECONOMY')).upper().replace(' ','_'),'economy'),re.I)
def _same_page(url,start_url):
 if not start_url:return False
 a,b=urlsplit(url or ''),urlsplit(start_url);return (a.netloc,a.path.rstrip('/'),a.query)==(b.netloc,b.path.rstrip('/'),b.query)
def results_check(obs,goal,start_url=''):
 """Validación de resultados con evidencia Python. Sólo cuenta si no seguimos en la URL inicial del formulario o si la URL es de resultados."""
 v=validate_results(obs.get('url',''),obs.get('full_text') or obs.get('text',''),goal)
 left_start=bool(start_url) and not _same_page(obs.get('url'),start_url)
 v['on_results_page']=bool(v['url_looks_like_results'] or left_start)
 return v
def _currency_done(obs):
 els=[e for e in obs.get('elements',[]) if 'currency' in (e.get('semantic_hints') or {})]
 if not els:return True
 for e in els:
  if e.get('tag')=='input' and e.get('type') in ('checkbox','radio') or e.get('role') in ('switch','checkbox','radio'):
   if e.get('checked'):return True
  elif re.search(r'usd|us\$',(e.get('value') or '')+' '+(e.get('text') or ''),re.I):return True
 return False
def determine_state(obs,goal,skipped=(),start_url='',confirmed=()):
 rs=obs.get('role_state') or {};fs=obs.get('form_summary') or {};skipped=set(skipped);confirmed=set(confirmed)
 v=results_check(obs,goal,start_url)
 if v['on_results_page'] and v['route_ok'] and v['departure_ok'] and v['return_ok']:
  if v['ok'] and v['currency']!='USD' and v['native_usd_option'] and 'SET_CURRENCY' not in skipped and not _currency_done(obs):return 'SET_CURRENCY'
  if v['ok'] and v['currency']!='USD' and v['native_usd_option'] and 'SET_CURRENCY' not in skipped:return 'EXTRACT_TOTAL'  # el switch USD ya está activo: esperar a que la página recalcule los precios
  return 'COMPLETE' if v['ok'] else ('EXTRACT_TOTAL' if v['passengers_ok'] is not False else 'VALIDATE_RESULTS')
 if fs.get('possible_site_search',0)>=.7 and fs.get('possible_flight_search_form',0)<.45:return 'LOCATE_FORM'
 if fs.get('possible_flight_search_form',0)<.4:return 'LOCATE_FORM'
 if 'SET_TRIP_TYPE' not in skipped and goal.get('return_date') and not rs.get('return_date') and obs.get('trip_round'):return 'SET_TRIP_TYPE'
 o,d=str(goal.get('origin','')).upper(),str(goal.get('destination','')).upper()
 nonempty=lambda role:_any_val(rs,role,lambda v:True)
 checks=[('SET_ORIGIN',lambda:_any_val(rs,'origin',lambda v:o in v.upper()) or ('origin' in confirmed and nonempty('origin'))),
         ('SET_DESTINATION',lambda:_any_val(rs,'destination',lambda v:d in v.upper()) or ('destination' in confirmed and nonempty('destination'))),
         ('SET_DEPARTURE',lambda:_any_val(rs,'departure_date',lambda v:date_matches(v,goal['departure'])) or ('departure_date' in confirmed and nonempty('departure_date'))),
         ('SET_RETURN',lambda:(_any_val(rs,'return_date',lambda v:date_matches(v,goal['return_date'])) or ('return_date' in confirmed and nonempty('return_date'))) if goal.get('return_date') else True)]
 for name,ok in checks:
  if not ok():return name
 n=_adults(goal)
 if 'SET_PASSENGERS' not in skipped and (rs.get('adults') or rs.get('passengers')):
  vals=_vals(rs,'adults')+_vals(rs,'passengers')+[str(e.get('text','')) for e in obs.get('elements',[]) if 'passengers' in (e.get('semantic_hints') or {})]
  if not any(digits_token(v,n) for v in vals):return 'SET_PASSENGERS'
 cab=_cabin_re(goal)
 if 'SET_CABIN' not in skipped and rs.get('cabin') and not any(cab.search(v) for v in _vals(rs,'cabin')+[str(e.get('text','')) for e in obs.get('elements',[]) if 'cabin' in (e.get('semantic_hints') or {})]):return 'SET_CABIN'
 if 'SET_CURRENCY' not in skipped and rs.get('currency') and not _currency_done(obs):return 'SET_CURRENCY'
 return 'SUBMIT'
def state_guidance(state,goal):
 n=_adults(goal)
 g={'LOCATE_FORM':'Find the real flight-booking form (origin/destination/dates). Never use site/help search or content links (route-map, destinations, explore). Open the booking tab/entry only if the form is not already visible.',
 'SET_TRIP_TYPE':'Select round trip / ida y vuelta.',
 'SET_ORIGIN':f"Use fill_airport on the origin control with IATA {goal.get('origin')}.",
 'SET_DESTINATION':f"Use fill_airport on the destination control (not the origin) with IATA {goal.get('destination')}.",
 'SET_DEPARTURE':f"Use fill_date on the departure date control with iso {goal.get('departure')}.",
 'SET_RETURN':f"Use fill_date on the return date control with iso {goal.get('return_date')}.",
 'SET_PASSENGERS':f"Set adults to {n}. If a panel must be opened, click its toggle first; use click on the + stepper or select.",
 'SET_CABIN':f"Set cabin to {goal.get('cabin','ECONOMY')}.",
 'SET_CURRENCY':'Select native USD if the site offers it.',
 'SUBMIT':'All fields are validated. Activate the flight-search submit control.',
 'VALIDATE_RESULTS':'Results are loading or incomplete. Wait; do not click.',
 'EXTRACT_TOTAL':'Results visible but passengers/total not verified. Wait or fix passengers; do not click prices.',
 'COMPLETE':'Done.'}
 return g.get(state,'Continue safely.')
def enrich(obs,goal,skipped=(),start_url='',confirmed=()):
 x=dict(obs)
 x['trip_round']=any(e.get('semantic_hints',{}).get('trip_round') and not e.get('checked') for e in obs.get('elements',[]))
 state=determine_state(x,goal,skipped,start_url,confirmed);x['harness']={'state':state,'guidance':state_guidance(state,goal),'state_order':STATES,'skipped':sorted(skipped)};return x
