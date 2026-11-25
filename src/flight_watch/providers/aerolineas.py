from __future__ import annotations
from datetime import datetime
from pathlib import Path
import json,re
from ..browser import BrowserSession
from ..domain import Observation
from ..fx import ars_to_usd
BASE=Path(__file__).resolve().parents[3]
URL='https://www.aerolineas.com.ar/?activeTab=searchBox'
def _diag(page,reason,stage='unknown'):
 d=BASE/'data'/'diagnostics';d.mkdir(parents=True,exist_ok=True);stamp=datetime.now().strftime('%Y%m%d_%H%M%S');root=d/f'aerolineas_{stamp}'
 try:page.screenshot(path=str(root.with_suffix('.png')),full_page=True)
 except Exception:pass
 try:root.with_suffix('.html').write_text(page.content(),encoding='utf-8')
 except Exception:pass
 root.with_suffix('.json').write_text(json.dumps({'provider':'aerolineas','stage':stage,'reason':reason,'url':page.url,'title':page.title()},ensure_ascii=False,indent=2),encoding='utf-8')
def _money(text,currency='USD'):
 out=[]
 for m in re.finditer(rf'{currency}\s*([\d.,]+)',text,re.I):
  raw=m.group(1);raw=raw.replace('.','').replace(',','.') if ',' in raw else raw.replace('.','')
  try:out.append(float(raw))
  except ValueError:pass
 return out
def _airport(page,kind,iata):
 sel='.suggestion-input-sb-origin' if kind=='origin' else '.suggestion-input-sb-destination'
 loc=page.locator(sel).first
 loc.click();loc.fill(iata);page.wait_for_timeout(1200)
 # This exact keyboard flow yielded 0 origin/destination validations in 0.11.5.
 page.keyboard.press('ArrowDown');page.wait_for_timeout(150);page.keyboard.press('Enter');page.wait_for_timeout(500)
 value=loc.input_value().strip();page.keyboard.press('Tab');page.wait_for_timeout(250)
 if iata.upper() not in value.upper():raise RuntimeError(f'{kind} no confirmado: {value!r}')
 return value

def _dates(page,depart,ret):
 # Verified from 2026-11-24 diagnostic DOM: ids from-date and to-date.
 f=page.locator('#from-date');t=page.locator('#to-date')
 if f.count()!=1 or t.count()!=1:raise RuntimeError('No se encontraron #from-date / #to-date')
 # React controlled fields accept real keyboard editing more reliably than locator.fill on this page.
 f.click();page.keyboard.press('Meta+A');page.keyboard.type(depart.strftime('%d/%m/%Y'));page.keyboard.press('Tab');page.wait_for_timeout(300)
 t.click();page.keyboard.press('Meta+A');page.keyboard.type(ret.strftime('%d/%m/%Y'));page.keyboard.press('Tab');page.wait_for_timeout(300)
def _passengers(page,adults,children):
 if adults==1 and children==0:return
 page.locator('#cabin-passengers').click()
 for _ in range(max(0,adults-1)):page.locator('.add-adt').click()
 for _ in range(max(0,children)):page.locator('.add-chd').click()
 page.keyboard.press('Escape')
def _verified_ars_totals(text):
 # Only amounts in a local context explicitly containing Total/Tarifa final/Precio final.
 # Reject installment, ancillary and homepage promotion contexts.
 lines=[x.strip() for x in text.splitlines() if x.strip()]
 out=[]
 for i,line in enumerate(lines):
  context=" | ".join(lines[max(0,i-2):min(len(lines),i+3)])
  if not re.search(r"(?:total|tarifa\s+final|precio\s+final)",context,re.I):continue
  if re.search(r"(?:cuota|por\s+mes|equipaje|asiento|desde)",context,re.I):continue
  for value in _money(line,'ARS'):
   if value>=50000:out.append(value)
 return sorted(set(out))

def _is_results_page(page):
 url=page.url.lower()
 if 'activetab=searchbox' in url:return False
 if url.rstrip('/') in ('https://www.aerolineas.com.ar','https://www.aerolineas.com.ar'):return False
 return True

def _network_observer(page):
 events=[]
 def request(req):
  if req.resource_type in ('xhr','fetch','document'):
   events.append({'kind':'request','method':req.method,'type':req.resource_type,'url':req.url,'post_data':(req.post_data or '')[:2000]})
 def response(res):
  req=res.request
  if req.resource_type in ('xhr','fetch','document'):
   events.append({'kind':'response','status':res.status,'type':req.resource_type,'url':res.url,'content_type':res.headers.get('content-type','')})
 page.on('request',request);page.on('response',response)
 return events

def _validation_messages(page):
 selectors=['[role="alert"]','.error','.validation-error','.MuiFormHelperText-root','[class*="error"]']
 out=[]
 for sel in selectors:
  try:
   for t in page.locator(sel).all_inner_texts():
    t=t.strip()
    if t and t not in out:out.append(t)
  except Exception:pass
 return out[:30]

class AerolineasProvider:
 name='aerolineas';experimental=True;last_status='sin ejecutar'
 def search(self,r,visible=False):
  a,c,b=r.counts()
  if b:raise ValueError('Aerolíneas experimental todavía no cotiza bebés de forma verificable.')
  with BrowserSession(self.name,visible) as s:
   p=s.page;stage='home';self.last_status='iniciando';network=_network_observer(p);popups=[];p.on('popup',lambda x: popups.append(x))
   try:
    p.goto(URL,wait_until='domcontentloaded',timeout=60000);p.wait_for_selector('.suggestion-input-sb-origin',timeout=30000)
    stage='cookies'
    for txt in ['Aceptar solo las esenciales','Aceptar']:
     try:
      q=p.get_by_role('button',name=re.compile(f'^{txt}$',re.I))
      if q.count():q.first.click(timeout=2500);break
     except Exception:pass
    stage='airports';self.last_status='completando origen/destino';_airport(p,'origin',r.origin);_airport(p,'destination',r.destination)
    stage='dates';self.last_status='completando fechas';_dates(p,r.departure,r.return_date)
    stage='passengers';self.last_status='ajustando pasajeros';_passengers(p,a,c)
    # Exact-date monitoring: the diagnostic showed flexible dates checked by default. Turn it off.
    stage='flex-dates';self.last_status='desactivando fechas flexibles';flex=p.locator('input[name="flex-dates"]').first
    if flex.count() and flex.is_checked():
     # Click the unique input/control itself; the page has two LABEL elements with the same visible text.
     try:flex.uncheck(force=True,timeout=3000)
     except Exception:flex.click(force=True,timeout=3000)
     p.wait_for_timeout(250)
    stage='pre-submit';pre_validations=_validation_messages(p)
    if any(re.search(r'origen',x,re.I) for x in pre_validations):
     reason='Validación del sitio antes de submit: '+' | '.join(pre_validations)
     self.last_status=reason;_diag(p,reason,stage);return []
    stage='submit';self.last_status='instrumentando submit'
    before={'url':p.url,'origin':p.locator('.suggestion-input-sb-origin').input_value(),'destination':p.locator('.suggestion-input-sb-destination').input_value(),'from_date':p.locator('#from-date').input_value(),'to_date':p.locator('#to-date').input_value(),'flex_checked':p.locator('input[name="flex-dates"]').first.is_checked() if p.locator('input[name="flex-dates"]').count() else None}
    p.keyboard.press('Escape');p.wait_for_timeout(400);btn=p.locator('#search-flights');btn.scroll_into_view_if_needed();p.wait_for_timeout(300)
    try:
     btn.click(timeout=3500)
     submit_mode='playwright-normal'
    except Exception as click_error:
     msg=str(click_error)
     if 'intercepts pointer events' not in msg:raise
     # DayPicker/header overlays are visual layers. Native HTMLElement.click() dispatches the
     # button's real DOM click handler without fabricating pointer coordinates.
     btn.evaluate('(el) => el.click()')
     submit_mode='dom-native-after-overlay'
    self.last_status=f'submit_mode={submit_mode}'
    p.wait_for_timeout(15000);after_url=p.url;validations=_validation_messages(p)
    report={'provider':'aerolineas','stage':'network-observer','before':before,'after_url':after_url,'popups':[x.url for x in popups],'validations':validations,'submit_mode':submit_mode,'network':network[-200:]}
    d=BASE/'data'/'diagnostics';d.mkdir(parents=True,exist_ok=True);stamp=datetime.now().strftime('%Y%m%d_%H%M%S');(d/f'aerolineas_network_{stamp}.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    stage='results';self.last_status=f'submit={submit_mode}; network observer: {len(network)} eventos; url_changed={after_url!=before["url"]}; popups={len(popups)}; validaciones={len(validations)}'
    # Positive transition evidence: URL changed, popup opened, or search backend XHR/fetch observed.
    relevant=[x for x in network if x.get('type') in ('xhr','fetch') and re.search(r'(availability|offers?|shopping/requests|flight-search|booking/search)',x.get('url',''),re.I) and '/rules/shopping/searchbox' not in x.get('url','')]
    target=popups[-1] if popups else p
    if not (after_url!=before['url'] or popups or relevant):
     reason=self.last_status+'; submit sin transición verificable.'
     self.last_status=reason;_diag(p,reason,stage);return []
    if popups:target.wait_for_load_state('domcontentloaded',timeout=30000)
    target.wait_for_timeout(3000);text=target.locator('body').inner_text();self.last_status+='; analizando resultado'
    usd=[x for x in _money(text,'USD') if x>=100]
    if usd:
     batch=datetime.now().strftime('%Y%m%d%H%M%S%f');self.last_status=f'resultado USD verificado: {min(usd):.2f}';return [Observation(self.name,r,min(usd),'USD',datetime.now(),target.url,'AR',None,'Mejor USD verificable',batch)]
    ars=_verified_ars_totals(text) if '_verified_ars_totals' in globals() else []
    if ars:
     original=min(ars);usd_value,rate=ars_to_usd(original)
     if usd_value>=100:
      detail=json.dumps({'original_price':original,'original_currency':'ARS','normalized_price_usd':usd_value,'fx_rate':rate},ensure_ascii=False);batch=datetime.now().strftime('%Y%m%d%H%M%S%f');self.last_status=f'total ARS {original:.0f} normalizado USD {usd_value:.2f}';return [Observation(self.name,r,usd_value,'USD',datetime.now(),target.url,'AR',None,detail,batch)]
    reason=self.last_status+'; transición detectada pero sin total verificable.';self.last_status=reason;_diag(target,reason,stage);return []
   except Exception as e:self.last_status=f'fallo en stage={stage}: {type(e).__name__}: {e}';_diag(p,f'{type(e).__name__}: {e}',stage);return []
 def replay(self,r,profile_id=''):
  from playwright.sync_api import sync_playwright
  import uuid
  pid=profile_id or uuid.uuid4().hex
  pw=sync_playwright().start();d=BASE/'data'/'browser'/'replays'/pid;d.mkdir(parents=True,exist_ok=True);ctx=pw.chromium.launch_persistent_context(str(d),headless=False,locale='es-AR');page=ctx.pages[0] if ctx.pages else ctx.new_page()
  page.goto(URL,wait_until='domcontentloaded',timeout=60000);page.wait_for_selector('.suggestion-input-sb-origin',timeout=30000)
  _airport(page,'origin',r.origin);_airport(page,'destination',r.destination);_dates(page,r.departure,r.return_date)
  a,c,b=r.counts()
  if not b:_passengers(page,a,c)
  flex=page.locator('input[name="flex-dates"]').first
  if flex.count() and flex.is_checked():
   try:flex.uncheck(force=True,timeout=3000)
   except Exception:flex.click(force=True,timeout=3000)
  page.keyboard.press('Escape');page.wait_for_timeout(400);btn=page.locator('#search-flights');btn.scroll_into_view_if_needed();page.wait_for_timeout(300)
  try:btn.click(timeout=3500)
  except Exception as e:
   if 'intercepts pointer events' not in str(e):raise
   btn.evaluate('(el) => el.click()')
  page.wait_for_timeout(3000)
  return pw,ctx,page

