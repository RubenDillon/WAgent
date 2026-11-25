from __future__ import annotations
import re
# Evidencia "fuerte": atributos del propio control. nearby_text/text de contenedores NO cuentan como evidencia fuerte.
STRONG=('id_attr','name','aria_label','labelledby','label','placeholder','autocomplete','class_attr','data_attrs')
FIELD_ROLES=('origin','destination','departure_date','return_date','passengers','adults','cabin','currency')
def norm(v):return re.sub(r'\s+',' ',str(v or '').lower()).strip()
def words(v):
 """Tokeniza camelCase/kebab/snake para que 'from-date' y 'fromDate' produzcan 'from date'."""
 s=re.sub(r'([a-z])([A-Z])',r'\1 \2',str(v or ''));s=re.sub(r'[_\-:./\[\]{}"\',]+',' ',s)
 return re.sub(r'\s+',' ',s.lower()).strip()
def _p(x):return re.compile(x,re.I)
P={
 'origin':_p(r'\b(origin|origen|departing from|leaving from|depart from|flying from|desde|salida desde|from airport|from city)\b'),
 'destination':_p(r'\b(destination|destino|arriving at|arrive at|flying to|going to|hacia|where to|to airport|to city)\b'),
 'departure_date':_p(r'\b(departure date|depart date|departure|depart|outbound|fecha de salida|fecha de ida|partida|start date|from date|date from|leave on)\b'),
 'return_date':_p(r'\b(return date|return|inbound|regreso|vuelta|fecha de regreso|fecha de vuelta|end date|to date|date to)\b'),
 'adults':_p(r'\b(adults?|adultos?|adt)\b'),
 'passengers':_p(r'\b(passengers?|travell?ers?|pax|guests?|pasajeros?|viajeros?)\b'),
 'cabin':_p(r'\b(cabin|cabina|travel class|fare class|class|clase)\b'),
 'currency':_p(r'\b(currency|moneda|pay in usd|pago en usd|payment currency)\b'),
}
ROUND=_p(r'^(round ?trip|ida y vuelta|return trip)$');ONEWAY=_p(r'^(one ?way|solo ida|ida|oneway)$')
BOOKING_ENTRY=_p(r'^(book|book a trip|book flights?|flights?|vuelos|reservar|reservar vuelos?|buscar vuelos|search flights)$')
IS_DATE=_p(r'\b(date|fecha|dd ?/ ?mm|mm ?/ ?dd|yyyy|aaaa)\b')
ANCH_FROM=_p(r'^from( where| city| airport)?$');ANCH_TO=_p(r'^to( where| city| airport)?$');SWAP=_p(r'\b(swap|switch|reverse|invert|exchange|intercambiar|invertir)\b')
FLIGHT_SEARCH=_p(r'\b(search|find|book|show|buscar|reservar|ver)\s+(for\s+)?(flights?|vuelos?|trips?)\b')
GENERIC_SEARCH=_p(r'^(search|buscar|go|submit|continue|continuar)$')
CONTENT_HREF=('route-map','find-your-destination','travel-planning-center','destinations','explore')
SITE_SEARCH_RAW=('header-search','header:search','site-search','sitesearch','help center','try asking me a question','search this site','buscar en el sitio')
def _editable(e):return e.get('tag') in ('input','select','textarea') or e.get('role') in ('combobox','textbox','spinbutton') or bool(e.get('contenteditable'))
def navigation_hints(e):
 raw=' '.join(norm(e.get(k)) for k in ('id_attr','name','aria_label','data_attrs','text','href','class_attr'))
 href=norm((e.get('href') or '')+' '+' '.join(re.findall(r'"data-href":"([^"]*)"',e.get('data_attrs') or '')));out={}
 if any(x in raw for x in SITE_SEARCH_RAW):out['site_search']=.99
 if e.get('in_header') and e.get('tag') in ('button','a','input') and GENERIC_SEARCH.match(norm(e.get('aria_label') or e.get('text'))):out['site_search']=max(out.get('site_search',0),.95)
 if any(x in href for x in CONTENT_HREF):out['content_navigation']=.99
 return out
def hints(e):
 tag=e.get('tag','');role=e.get('role','');typ=norm(e.get('type'));out={}
 fields=[words(e.get(k)) for k in STRONG];fields=[f for f in fields if f]
 txt=words(e.get('text'))
 if txt and len(txt)<=40 and tag!='input':fields.append(txt)
 control=_editable(e) or tag=='button' or role in ('button','tab','switch')
 field_ok=control and not (tag=='input' and typ in ('submit','button','image','checkbox','radio','hidden','reset'))
 def hit(r):return any(P[r].search(f) for f in fields)
 if field_ok:
  if typ in ('date','datetime-local') or any(IS_DATE.search(f) for f in fields):
   r_,d_=hit('return_date'),hit('departure_date')
   if r_:out['return_date']=.9
   if d_:out['departure_date']=.9  # un único control 'Depart - Return' cubre ambos roles
   if not r_ and not d_:out['date']=.5
  else:
   if not any(SWAP.search(f) for f in fields):
    if hit('origin') or any(ANCH_FROM.match(f) for f in fields):out['origin']=.9
    if hit('destination') or any(ANCH_TO.match(f) for f in fields):out['destination']=.9
   if not out and _editable(e) and tag=='input':
    near=words(e.get('nearby_text'))
    if 0<len(near)<=80:
     o,d=bool(P['origin'].search(near)),bool(P['destination'].search(near))
     if o!=d:out['origin' if o else 'destination']=.5
  for r in ('adults','passengers','cabin','currency'):
   if hit(r):out[r]=.9
  if (tag in ('button','select') or role=='combobox') and re.search(r'\b(economy|business|premium|turista|ejecutiva|first)\b',txt+' '+words(e.get('value'))):out['cabin']=max(out.get('cabin',0),.7)
 toggle=(tag=='input' and typ in ('checkbox','radio')) or role in ('switch','checkbox','radio')
 if toggle and any(P['currency'].search(f) for f in fields+[words(e.get('text'))]):out['currency']=.9
 if tag in ('button','a','input') or role=='button':
  direct=' '.join(words(e.get(k)) for k in ('id_attr','name','aria_label','text','class_attr','value') if e.get(k))
  if len(direct)<=120 and FLIGHT_SEARCH.search(direct):out['flight_search']=.92
 if tag in ('button','a','input','label') or role in ('tab','radio','button','option','switch'):
  t=norm(e.get('aria_label') or e.get('text') or e.get('label') or e.get('value'))
  if len(t)<=30:
   if ROUND.match(t):out['trip_round']=.9
   elif ONEWAY.match(t):out['trip_oneway']=.9
   if BOOKING_ENTRY.match(t) and not (e.get('href') and any(x in norm(e.get('href')) for x in CONTENT_HREF)):out['booking_entry']=.7
 out.update(navigation_hints(e))
 if out.get('site_search',0)>=.9:out.pop('flight_search',None)
 if out.get('content_navigation'):out.pop('flight_search',None)
 return {k:round(v,2) for k,v in out.items()}
def form_summary(els):
 found={}
 for e in els:
  for k,v in e.get('semantic_hints',{}).items():found[k]=max(found.get(k,0),v)
 return {'possible_flight_search_form':round(sum(found.get(k,0) for k in ('origin','destination','departure_date','return_date'))/4,2),'possible_site_search':found.get('site_search',0),'roles_found':found}
def role_state(els):
 out={}
 for e in els:
  if e.get('disabled'):continue
  for r,s in (e.get('semantic_hints') or {}).items():
   if r in FIELD_ROLES and s>=.5:out.setdefault(r,[]).append({'id':e['id'],'value':(e.get('value') or e.get('text') or '').strip(),'score':s})
 return out
def finalize(els):
 """Heurísticas que necesitan ver el conjunto: fechas genéricas por orden DOM y 'Search' genérico dentro de un form de vuelos."""
 explicit=lambda r:any(r in (e.get('semantic_hints') or {}) for e in els)
 gen=[e for e in els if 'date' in (e.get('semantic_hints') or {}) and _editable(e)]
 if gen and not explicit('departure_date'):
  gen[0]['semantic_hints']['departure_date']=.6;gen=gen[1:]
 if gen and not explicit('return_date'):gen[0]['semantic_hints']['return_date']=.6
 if form_summary(els)['possible_flight_search_form']>=.5 and not explicit('flight_search'):
  for e in els:
   h=e.setdefault('semantic_hints',{})
   if e.get('tag') in ('button','input') and not e.get('in_header') and not h.get('site_search') and GENERIC_SEARCH.match(norm(e.get('text') or e.get('value'))):h['flight_search']=.6;break
def annotate(els):
 for e in els:e['semantic_hints']=hints(e)
 finalize(els)
 return els
