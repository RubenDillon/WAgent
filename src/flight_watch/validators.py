"""Validadores deterministas. El LLM nunca decide si un precio o un campo es correcto: lo decide Python."""
from __future__ import annotations
import re
from datetime import date
MONTHS={'en':['january','february','march','april','may','june','july','august','september','october','november','december'],
        'es':['enero','febrero','marzo','abril','mayo','junio','julio','agosto','septiembre','octubre','noviembre','diciembre']}
SHORT={m[:3]:i+1 for lang in MONTHS.values() for i,m in enumerate(lang)};SHORT.update({'sep':9,'set':9,'ene':1,'abr':4,'ago':8,'dic':12,'apr':4,'aug':8,'dec':12,'jan':1})
def _iso(v):
 if isinstance(v,date):return v
 return date.fromisoformat(str(v)[:10])
def _month_words(d):
 names={MONTHS['en'][d.month-1],MONTHS['es'][d.month-1]};names|={n[:3] for n in names};return '|'.join(sorted(names,key=len,reverse=True))
def date_patterns(iso):
 """Regex que reconocen la fecha `iso` en formatos habituales. Si el texto trae año, debe ser el correcto."""
 d=_iso(iso);dd,mm,yy=d.day,d.month,d.year;mw=_month_words(d)
 return [
  rf'(?<!\d){yy}[-/.]?0?{mm}[-/.]?0?{dd}(?!\d)',                                         # 2027-07-17 / 20270717
  rf'(?<!\d)0?{dd}[/.\-]0?{mm}(?:[/.\-](?:{yy}|{yy%100:02d}))?(?![/.\-]?\d)',            # 17/07/2027, 17/07 (no 17/07/2026)
  rf'(?<!\d)0?{mm}[/.\-]0?{dd}[/.\-]{yy}(?!\d)',                                       # 07/17/2027
  rf'(?<!\d){dd}\s*(?:de\s+)?(?:{mw})\b(?!\s*(?:de\s+)?(?!{yy})20\d\d)',            # 17 de julio [de 2027]
  rf'\b(?:{mw})\.?\s+0?{dd}(?!\d)(?!,?\s*(?!{yy})20\d\d)',                           # Jul 17 [, 2027]
 ]
def date_matches(value,iso):
 s=str(value or '').strip().lower()
 return bool(s) and any(re.search(p,s,re.I) for p in date_patterns(_iso(iso)))
def date_in_text(text,iso):return date_matches(text,iso)
def digits_token(value,n):return bool(re.search(rf'(?<!\d){int(n)}(?!\d)',str(value or '')))
# ---------------------------------------------------------------- dinero
CUR={'USD':'USD','US$':'USD','U$S':'USD','U$D':'USD','ARS':'ARS','EUR':'EUR','€':'EUR','BRL':'BRL','CLP':'CLP','MXN':'MXN','COP':'COP'}
CUR_RE=r'(USD|US\$|U\$S|U\$D|ARS|EUR|€|BRL|CLP|MXN|COP)'
AMOUNT_RE=r'(\d{1,3}(?:[.,\s]\d{3})+(?:[.,]\d{1,2})?|\d+(?:[.,]\d{1,2})?)'
REJECT=re.compile(r'(cuota|installment|per month|por mes|mensual|monthly|equipaje|baggage|luggage|\bbag\b|asiento|seat|pre ?partida|post ?partida|fee|cargo|tasa|surcharge|milla|miles|points|puntos|desde|from|starting|a partir)',re.I)
def parse_amount(raw):
 s=re.sub(r'\s','',str(raw))
 if ',' in s and '.' in s:
  dec=',' if s.rfind(',')>s.rfind('.') else '.';thou='.' if dec==',' else ','
  s=s.replace(thou,'').replace(dec,'.')
 elif ',' in s or '.' in s:
  sep=',' if ',' in s else '.'
  if re.fullmatch(rf'\d{{1,3}}(?:\{sep}\d{{3}})+',s):s=s.replace(sep,'')
  else:s=s.replace(',','.')
 try:return float(s)
 except ValueError:return None
def money_in_line(line,nxt=''):
 """Importes de una línea. Soporta 'USD 1.234', '1.234 USD', '$1,234 USD' y número solo + moneda en la línea siguiente."""
 out=[];s=line.strip()
 for m in re.finditer(rf'{CUR_RE}\s*{AMOUNT_RE}',s,re.I):
  a=parse_amount(m.group(2))
  if a is not None:out.append((a,CUR[m.group(1).upper()]))
 for m in re.finditer(rf'(?<![\d.,]){AMOUNT_RE}\s*{CUR_RE}(?![A-Za-z])',s,re.I):
  a=parse_amount(m.group(1))
  if a is not None and (a,CUR[m.group(2).upper()]) not in out:out.append((a,CUR[m.group(2).upper()]))
 if not out and re.fullmatch(AMOUNT_RE,s):
  m=re.match(rf'\s*{CUR_RE}(?![A-Za-z])',nxt or '',re.I)
  if m:
   a=parse_amount(s)
   if a is not None:out.append((a,CUR[m.group(1).upper()]))
 return out
MIN_PLAUSIBLE={'USD':100,'EUR':100,'ARS':50000,'BRL':500,'CLP':50000,'MXN':1000,'COP':200000}
def extract_prices(text):
 lines=[x.strip() for x in (text or '').splitlines() if x.strip()];out=[]
 for i,line in enumerate(lines):
  prev=lines[i-1] if i else '';nxt=lines[i+1] if i+1<len(lines) else ''
  for a,c in money_in_line(line,nxt):
   bare=not re.search(r'[A-Za-zÀ-ÿ]{4,}',re.sub(CUR_RE,'',line,flags=re.I));ctx=line+' '+prev if bare else line
   if REJECT.search(ctx):continue
   if a<MIN_PLAUSIBLE.get(c,1):continue
   out.append({'amount':a,'currency':c,'line':line[:120]})
 return out
# ---------------------------------------------------------------- resultados
FLEX_URL=re.compile(r'flex-?dates?-?calendar|flexible-?dates?-?calendar',re.I)  # calendario de precios "desde" por fecha: no es la lista de vuelos de la fecha pedida
RESULT_URL=re.compile(r'(flights?-?(offers|results|list|select|availability)|/(results|availability|select|search-results|shopping|booking)/|/flights/|vuelos)',re.I)
def validate_results(url,text,goal):
 """Evalúa si la página es un resultado de vuelos para `goal`. Devuelve evidencias, no una decisión del LLM."""
 from .navigation_guard import off_task
 url=url or '';text=text or '';blob=url+'\n'+text
 off,why=off_task(url)
 o,d=str(goal.get('origin','')).upper(),str(goal.get('destination','')).upper()
 route=bool(o and d and re.search(rf'\b{o}\b',blob) and re.search(rf'\b{d}\b',blob))
 dep=bool(goal.get('departure') and date_in_text(blob,goal['departure']));ret=bool(goal.get('return_date') and date_in_text(blob,goal['return_date']))
 adults=len([a for a in goal.get('ages',[30]) if a>=18]);pax_ok=None
 m=re.search(r'(?:adt|adults?)=(\d+)',url,re.I)
 if m:pax_ok=int(m.group(1))==adults
 else:
  t=re.search(r'(\d+)\s*(?:pasajeros?|passengers?|adultos?|adults?)',text,re.I)
  if t:pax_ok=int(t.group(1))>=adults
 prices=extract_prices(text);usd=[p for p in prices if p['currency']=='USD'];other=[p for p in prices if p['currency']!='USD']
 native_usd_option=bool(re.search(r'(pago en usd|pay in usd|pay with usd|show prices in usd|prices in usd)',text,re.I))
 chosen=None;note=''
 if usd:chosen=min(usd,key=lambda p:p['amount'])
 elif other:chosen=min(other,key=lambda p:p['amount']);note='sin USD nativo'+('; el sitio ofrece pago en USD' if native_usd_option else '')
 basis='total' if re.search(r'\b(total|tarifa final|precio final)\b',text,re.I) else ('per_passenger' if re.search(r'(por (adulto|persona|pasajero)|per (adult|person|passenger)|each way)',text,re.I) else 'unknown')
 reasons=[];flex=bool(FLEX_URL.search(url))
 if flex:reasons.append('calendario de fechas flexibles, no resultados de la fecha pedida')
 if off:reasons.append(f'off_task:{why}')
 if not route:reasons.append('ruta no visible')
 if not (dep and ret):reasons.append('fechas no visibles')
 if pax_ok is False:reasons.append('pasajeros no coinciden')
 if not chosen:reasons.append('sin precio verificable')
 ok=not off and not flex and route and dep and ret and pax_ok is not False and bool(chosen)
 return {'ok':ok,'url_looks_like_results':bool(RESULT_URL.search(url)) and not flex,'flex_calendar':flex,'route_ok':route,'departure_ok':dep,'return_ok':ret,'passengers_ok':pax_ok,'currency':chosen['currency'] if chosen else None,'native_usd':bool(usd),'native_usd_option':native_usd_option,'price_candidate':chosen,'price_count':len(prices),'note':note,'price_basis':basis,'reasons':reasons}
