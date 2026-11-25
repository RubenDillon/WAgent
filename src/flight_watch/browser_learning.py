from __future__ import annotations
import hashlib,json,os,re
from datetime import date
from pathlib import Path
from .semantic_forms import annotate,form_summary,role_state
from .validators import date_matches,date_patterns,digits_token
BASE=Path(__file__).resolve().parents[2]
ALLOWED={'click','fill','press','wait','back','restart','fill_airport','fill_date','select','check','uncheck','finish','fail'}
MAX_ELEMENTS=260
# --------------------------------------------------------------------------- JS
OBSERVE_JS=r"""(opts)=>{
 const SEL='input,button,select,textarea,a,[role=button],[role=option],[role=combobox],[role=switch],[role=tab],[role=checkbox],[role=radio],[role=spinbutton],[role=menuitem],[contenteditable=""],[contenteditable=true]';
 const ATTR='data-fw-id';
 function walk(root,sel,acc){for(const e of root.querySelectorAll(sel))acc.push(e);for(const h of root.querySelectorAll('*'))if(h.shadowRoot)walk(h.shadowRoot,sel,acc);return acc}
 for(const e of walk(document,'['+ATTR+']',[]))e.removeAttribute(ATTR);
 function deepTop(x,y){let el=document.elementFromPoint(x,y);let g=0;while(el&&el.shadowRoot&&g++<8){const i=el.shadowRoot.elementFromPoint(x,y);if(!i||i===el)break;el=i}return el}
 function rel(a,b){if(!a||!b)return false;if(a===b||a.contains(b)||b.contains(a))return true;const ra=a.getRootNode&&a.getRootNode();return !!(ra&&ra.host&&(ra.host===b||b.contains(ra.host)))}
 const modals=walk(document,'dialog[open],[role=dialog],[aria-modal=true]',[]).filter(m=>{const r=m.getBoundingClientRect(),s=getComputedStyle(m);return r.width>10&&r.height>10&&s.visibility!=='hidden'&&s.display!=='none'});
 const els=walk(document,SEL,[]);const out=[];let n=opts.start;const vw=innerWidth,vh=innerHeight;
 for(const e of els){
  const r=e.getBoundingClientRect(),st=getComputedStyle(e);
  const ct=(e.tagName==='INPUT'&&(e.type==='checkbox'||e.type==='radio'));
  if(r.width<=1||r.height<=1||st.visibility==='hidden'||st.display==='none')continue;
  if(Number(st.opacity)===0&&!ct)continue;
  const inView=r.bottom>0&&r.top<vh&&r.right>0&&r.left<vw;
  const modal=modals.find(m=>m.contains(e))||null;
  if(inView&&!ct){const x=Math.min(vw-1,Math.max(0,r.left+r.width/2)),y=Math.min(vh-1,Math.max(0,r.top+r.height/2));const top=deepTop(x,y);if(!rel(top,e))continue}
  else if(!inView&&modals.length&&!modal)continue;
  const id=n++;e.setAttribute(ATTR,String(id));
  const eid=e.id||'';let label='';
  if(eid){try{const l=document.querySelector('label[for="'+CSS.escape(eid)+'"]');if(l)label=(l.innerText||'').trim()}catch(_){}}
  if(!label){const l=e.closest('label');if(l)label=(l.innerText||'').trim()}
  let lb='';const lbid=e.getAttribute('aria-labelledby');if(lbid){lb=lbid.split(/\s+/).map(i=>{const x=document.getElementById(i);return x?(x.innerText||x.textContent||'').trim():''}).join(' ').trim()}
  const par=e.parentElement,near=par?(par.innerText||'').trim().slice(0,200):'',data={};
  for(const a of e.attributes)if(a.name.startsWith('data-')&&a.name!==ATTR)data[a.name]=a.value.slice(0,60);
  let opts2=null;if(e.tagName==='SELECT'){opts2=[...e.options].slice(0,14).map(o=>(o.text||'').trim().slice(0,40))}
  out.push({id,tag:e.tagName.toLowerCase(),role:e.getAttribute('role')||'',id_attr:eid,name:e.getAttribute('name')||'',type:e.getAttribute('type')||'',placeholder:e.getAttribute('placeholder')||'',aria_label:e.getAttribute('aria-label')||'',labelledby:lb.slice(0,80),autocomplete:e.getAttribute('autocomplete')||'',href:(e.getAttribute('href')||'').slice(0,160),class_attr:(typeof e.className==='string'?e.className:'').slice(0,100),label:label.slice(0,120),nearby_text:near,value:((e.value!==undefined&&e.tagName!=='BUTTON'?e.value:'')||'').toString().trim().slice(0,120),text:(e.innerText||e.value||'').toString().trim().slice(0,120),checked:e.checked===true||e.getAttribute('aria-checked')==='true'||e.getAttribute('aria-pressed')==='true'||e.getAttribute('aria-selected')==='true',disabled:e.disabled===true||e.getAttribute('aria-disabled')==='true',readonly:e.readOnly===true||e.getAttribute('aria-readonly')==='true',expanded:e.getAttribute('aria-expanded')||'',contenteditable:e.isContentEditable===true&&e.tagName!=='INPUT',data_attrs:JSON.stringify(data).slice(0,240),in_modal:!!modal,in_header:!!e.closest('header,[role=banner],nav'),offscreen:!inView,options:opts2});
  if(out.length>=opts.limit)break}
 const dialogs=modals.map(m=>(m.innerText||'').trim().slice(0,500)).filter(Boolean).slice(0,4);
 return {elements:out,dialogs,count:n}}"""
PICK_DAY_JS=r"""(opts)=>{
 function walk(root,acc){for(const e of root.querySelectorAll('[aria-label],[data-date],[data-day],[data-value],[title],td,[role=gridcell],button'))acc.push(e);for(const h of root.querySelectorAll('*'))if(h.shadowRoot)walk(h.shadowRoot,acc);return acc}
 for(const e of walk(document,[]))e.removeAttribute('data-fw-day');
 const res=opts.patterns.map(p=>new RegExp(p,'i'));
 const iso=opts.iso;let best=null;
 for(const e of walk(document,[])){
  const r=e.getBoundingClientRect(),st=getComputedStyle(e);if(r.width<=1||r.height<=1||st.visibility==='hidden'||st.display==='none')continue;
  if(e.disabled||e.getAttribute('aria-disabled')==='true'||/disabled|outside|unavailable/i.test(e.className&&e.className.toString?e.className.toString():''))continue;
  const lab=[e.getAttribute('aria-label'),e.getAttribute('data-date'),e.getAttribute('data-day'),e.getAttribute('data-value'),e.getAttribute('title')].filter(Boolean).join(' | ');
  if(!lab)continue;
  if(lab.length>80)continue;
  if(lab.indexOf(iso)>=0||res.some(re=>re.test(lab))){if(!best||(e.tagName==='BUTTON'||e.getAttribute('role')==='gridcell'||e.tagName==='TD')&&r.width*r.height<best.area){best={e,area:r.width*r.height}}}
 }
 if(best){best.e.setAttribute('data-fw-day','1');return {found:true}}
 return {found:false}}"""
CAL_OPEN_JS=r"""()=>{
 const MON='(january|february|march|april|may|june|july|august|september|october|november|december|enero|febrero|marzo|abril|mayo|junio|julio|agosto|septiembre|octubre|noviembre|diciembre)';
 const re=new RegExp(MON+'\\b.*\\b20\\d\\d|\\b20\\d\\d-\\d\\d-\\d\\d','i');let n=0;
 function walk(root){for(const e of root.querySelectorAll('button,td,[role=gridcell],[data-date]')){const r=e.getBoundingClientRect();if(r.width<=1||r.height<=1)continue;const l=[e.getAttribute('aria-label'),e.getAttribute('data-date')].filter(Boolean).join(' ');if(l&&l.length<=40&&re.test(l))n++}for(const h of root.querySelectorAll('*'))if(h.shadowRoot)walk(h.shadowRoot)}
 walk(document);return n>=20}"""
SEL_JS=r"""(el)=>{const t=(el.getAttribute('aria-selected')||'')+(el.getAttribute('aria-pressed')||'')+(el.getAttribute('aria-checked')||'');const c=(el.className&&el.className.toString?el.className.toString():'');return /true/.test(t)||/(^|[\s_-])(selected|active|chosen|range-start|range-end|start|end)([\s_-]|$)/i.test(c)}"""
NEXT_MONTH_JS=r"""()=>{
 function walk(root,acc){for(const e of root.querySelectorAll('button,[role=button]'))acc.push(e);for(const h of root.querySelectorAll('*'))if(h.shadowRoot)walk(h.shadowRoot,acc);return acc}
 const all=walk(document,[]);for(const e of all)e.removeAttribute('data-fw-next');
 const re=/(next|siguiente|forward|avanzar|mes siguiente|next month|›|»|→|>)/i,bad=/(search|buscar|continue|continuar|trip|viaje|vuelo|flight)/i;
 const CAL='[class*=calendar i],[class*=picker i],[class*=datepicker i],[role=dialog],[role=grid],[class*=daypicker i],[class*=month i]';
 const ok=e=>{const r=e.getBoundingClientRect(),st=getComputedStyle(e);if(r.width<=1||r.height<=1||st.visibility==='hidden'||st.display==='none'||e.disabled||e.getAttribute('aria-disabled')==='true')return false;const lab=(e.getAttribute('aria-label')||e.getAttribute('title')||e.innerText||'').trim();return lab.length<=48&&re.test(lab)&&!/(prev|anterior|back|previous)/i.test(lab)&&!bad.test(lab)};
 const cands=all.filter(ok);const inCal=cands.find(e=>e.closest(CAL));const pick=inCal||cands[0];
 if(pick){pick.setAttribute('data-fw-next','1');return true}return false}"""
BANNER_BTN=re.compile(r'^\s*(accept only essentials?|accept essentials?|only essential|use necessary cookies only|reject all|reject|decline|deny|rechazar( todo)?|aceptar solo (las )?esenciales|solo esenciales|necesarias|accept all( cookies)?|allow all( cookies)?|accept|i agree|agree|got it|ok|aceptar( todo| todas)?|entendido|continuar|save( preferences| settings)?|confirm my choices|close|cerrar)\s*$',re.I)
BANNER_ORDER=['essential','necessary','reject','decline','deny','rechaz','esencial','necesari','accept','allow','agree','aceptar','got it','ok','entendido','save','confirm','continu','close','cerrar']
BANNER_CONTAINER='[id*=cookie i],[class*=cookie i],[id*=consent i],[class*=consent i],[id*=onetrust i],[id*=privacy i],[class*=privacy i],[id*=gdpr i],[class*=gdpr i],[aria-label*=cookie i],[aria-label*=privacy i],[aria-label*=consent i],[id*=truste i],[class*=truste i],[class*=banner i],[role=dialog],[aria-modal=true]'
class LearningBrowser:
 def __init__(self,provider,start_url,page=None,headless=None,record_dir=None,profile=None,ephemeral=False):
  self.profile=profile;self.ephemeral=ephemeral;self.provider=provider;self.start_url=start_url;self.pw=self.ctx=None;self.page=page;self._external=page is not None
  self.headless=(os.getenv('FLIGHT_WATCH_HEADLESS','0')=='1') if headless is None else headless
  self.record_dir=Path(record_dir) if record_dir else None;self._frames={};self.last_obs=None;self._banner_tries=0
 def __enter__(self):
  if self._external:
   if self.start_url:self.page.goto(self.start_url,wait_until='domcontentloaded',timeout=60000)
   return self
  from playwright.sync_api import sync_playwright
  import tempfile
  self.pw=sync_playwright().start()
  profile=Path(tempfile.mkdtemp(prefix='fw_shadow_')) if self.ephemeral else Path(self.profile) if self.profile else BASE/'data'/'browser'/'learning'/self.provider.lower().replace(' ','_')
  self._profile_path=profile;profile.mkdir(parents=True,exist_ok=True)
  kw=dict(headless=self.headless,locale='es-AR',viewport={'width':1400,'height':1000})
  ch=os.getenv('FLIGHT_WATCH_CHANNEL','').strip()
  if ch:kw['channel']=ch
  self.ctx=self.pw.chromium.launch_persistent_context(str(profile),**kw)
  self.page=self.ctx.pages[0] if self.ctx.pages else self.ctx.new_page();self.page.goto(self.start_url,wait_until='domcontentloaded',timeout=60000);return self
 def __exit__(self,*_):
  if self._external:return
  try:self.ctx.close()
  except Exception:pass
  try:self.pw.stop()
  except Exception:pass
  if self.ephemeral:
   import shutil;shutil.rmtree(getattr(self,'_profile_path',''),ignore_errors=True)
 # ------------------------------------------------------------------ observación
 def _frames_to_scan(self):
  fr=[self.page.main_frame]
  for f in self.page.frames:
   if f is self.page.main_frame or f.url in ('','about:blank') or len(fr)>=5:continue
   try:
    box=f.frame_element().bounding_box()
    if box and box['width']>200 and box['height']>100:fr.append(f)
   except Exception:pass
  return fr
 def observe(self):
  try:self.page.wait_for_load_state('domcontentloaded',timeout=8000)
  except Exception:pass
  els=[];dialogs=[];self._frames={};start=0
  for fi,fr in enumerate(self._frames_to_scan()):
   try:r=fr.evaluate(OBSERVE_JS,{'start':start,'limit':MAX_ELEMENTS-len(els)})
   except Exception:
    if fi==0:
     self.page.wait_for_timeout(800)
     try:r=fr.evaluate(OBSERVE_JS,{'start':start,'limit':MAX_ELEMENTS-len(els)})
     except Exception:r={'elements':[],'dialogs':[],'count':start}
    else:continue
   for e in r['elements']:e['frame']=fi;self._frames[e['id']]=fr
   els+=r['elements'];dialogs+=r['dialogs'];start=r['count']
   if len(els)>=MAX_ELEMENTS:break
  annotate(els)
  try:title=self.page.title()
  except Exception:title=''
  obs={'url':self.page.url,'title':title,'elements':els,'dialogs':dialogs[:4],'form_summary':form_summary(els),'role_state':role_state(els),'text':self.page_text(3500),'full_text':self.page_text(60000)}
  self.last_obs=obs;return obs
 @staticmethod
 def signature(obs):
  """Firma pura (no reobserva): URL + estructura + valores de los controles relevantes."""
  parts=[(obs.get('url') or '').split('#')[0],'|'.join(d[:60] for d in obs.get('dialogs',[]))]
  for e in obs.get('elements',[])[:120]:parts.append(f"{e.get('tag')}|{e.get('role')}|{e.get('name')}|{e.get('id_attr')}|{e.get('value')}|{(e.get('text') or '')[:30]}|{e.get('checked')}|{e.get('expanded')}")
  return hashlib.sha256('\n'.join(parts).encode('utf-8','ignore')).hexdigest()[:20]
 def state_signature(self):return self.signature(self.observe())
 def page_text(self,limit=60000):
  try:return self.page.locator('body').inner_text(timeout=5000)[:limit]
  except Exception:return ''
 def snapshot_html(self):
  try:
   html=self.page.content()
   return re.sub(r'<script\b.*?</script>','',html,flags=re.S|re.I)
  except Exception:return ''
 # ------------------------------------------------------------------ localización
 def _loc(self,target_id):
  if not isinstance(target_id,int):raise ValueError(f'target_id debe ser entero; recibido={target_id!r}')
  fr=self._frames.get(target_id) or self.page
  q=fr.locator(f'[data-fw-id="{target_id}"]').first
  if not q.count():raise ValueError(f'target_id {target_id} ya no existe; reobservar')
  return q,fr
 # ------------------------------------------------------------------ banners
 def dismiss_banners(self,max_clicks=2):
  """Resuelve en Python banners de cookies/privacidad antes de que el LLM los vea. Prefiere la opción menos invasiva."""
  clicked=[]
  for _ in range(max_clicks):
   best=None
   for fr in self._frames_to_scan():
    try:
     cands=fr.locator(BANNER_CONTAINER).locator('button:visible,[role=button]:visible,a:visible,input[type=button]:visible,input[type=submit]:visible')
     n=min(cands.count(),60)
     for i in range(n):
      c=cands.nth(i)
      try:txt=(c.inner_text(timeout=300) or c.get_attribute('value') or c.get_attribute('aria-label') or '').strip()
      except Exception:continue
      if not txt or len(txt)>40 or not BANNER_BTN.match(txt):continue
      low=txt.lower();rank=next((k for k,w in enumerate(BANNER_ORDER) if w in low),len(BANNER_ORDER))
      if best is None or rank<best[0]:best=(rank,c,txt)
    except Exception:continue
   if not best:break
   try:best[1].click(timeout=2500);clicked.append(best[2]);self.page.wait_for_timeout(500)
   except Exception:break
  return clicked
 # ------------------------------------------------------------------ herramientas de dominio
 def _open_picker(self,q):
  """Delta y similares: el origen/destino es un botón que abre un modal con un input de búsqueda. Devuelve ese input."""
  q.click(timeout=3500);inp=None
  for _ in range(10):
   self.page.wait_for_timeout(300)
   for fr in self._frames_to_scan():
    try:
     c=fr.locator('[role=dialog] input:visible,[class*=modal i] input:visible,[class*=search i] input[type=text]:visible,[class*=predictive i] input:visible,input[role=combobox]:visible,input[aria-autocomplete]:visible')
     if c.count():inp=c.first;break
     f=fr.locator('input:focus:visible')
     if f.count():inp=f.first;break
    except Exception:continue
   if inp:return inp
  raise ValueError('el botón no abrió ningún campo de búsqueda de aeropuerto')
 def fill_airport(self,target_id,iata,role=None):
  if not isinstance(target_id,int) or not iata:raise ValueError('fill_airport requiere target_id entero e iata')
  iata=str(iata).upper();q,fr=self._loc(target_id)
  tag=q.evaluate('(e)=>e.tagName.toLowerCase()');dom_role=q.get_attribute('role') or ''
  btn=None
  if tag not in ('input','textarea','select') and dom_role not in ('combobox','textbox'):
   if tag!='button' and dom_role!='button':raise ValueError(f'fill_airport requiere campo editable o botón selector; target {target_id} es {tag} role={dom_role!r}')
   btn=q;q=self._open_picker(q);fr=self.page
  try:return self._fill_airport_input(q,fr,btn,iata,target_id,role)
  except Exception:
   if btn is not None:
    try:self.page.keyboard.press('Escape')
    except Exception:pass
   raise
 def _fill_airport_input(self,q,fr,btn,iata,target_id,role):
  opt=fr.locator('[role=option]:visible,li:visible,[class*=suggest]:visible,[class*=airport]:visible,[class*=autocomplete]:visible,[class*=result]:visible')
  def type_and_find():
   q.click()
   try:q.press('ControlOrMeta+A');q.press('Backspace')
   except Exception:pass
   q.fill(iata);found=[]
   for _ in range(8):
    self.page.wait_for_timeout(400);found=[]
    for i in range(min(opt.count(),150)):
     c=opt.nth(i)
     try:
      txt=c.inner_text(timeout=250).strip()
      if len(txt)<=200 and re.search(rf'\b{re.escape(iata)}\b',txt,re.I):found.append((len(txt),c,txt))
     except Exception:pass
    if found:break
   found.sort(key=lambda m:m[0]);return found
  def read_value():
   try:return q.input_value().strip()
   except Exception:return (q.inner_text() or '').strip()
  def chosen(value,opt_txt=''):  # la sugerencia se eligió de verdad si el input ya no contiene sólo lo tipeado (React Autosuggest exige elegir de la lista)
   return bool(value) and (value.upper()!=iata or opt_txt.strip().upper()==iata)
  clicked=False;matches=type_and_find();value='';how='keyboard'
  if btn is None:
   if matches:
    try:matches[0][1].click(timeout=2500);clicked=True;how='suggestion'
    except Exception:pass
    self.page.wait_for_timeout(700);value=read_value()
    if clicked and not chosen(value,matches[0][2]):clicked=False  # el click no eligió: reintento por teclado
   if not clicked:
    matches=type_and_find()  # reescribe el IATA y espera la lista (el provider manual necesita ~1.2 s)
    q.press('ArrowDown');self.page.wait_for_timeout(150);q.press('Enter');self.page.wait_for_timeout(600);how='keyboard';value=read_value()
  else:
   if matches:
    try:matches[0][1].click(timeout=2500);clicked=True
    except Exception:matches=[]
   if not clicked:q.press('ArrowDown');q.press('Enter')
   self.page.wait_for_timeout(700)
  if btn is not None:  # selector en modal: la confirmación es el texto del botón que lo abrió
   try:value=(btn.inner_text(timeout=1500) or '').strip()
   except Exception:value=''
   if not (clicked and re.search(rf'\b{re.escape(iata)}\b',value,re.I)):raise ValueError(f'selector no confirmó {iata}; botón={value[:80]!r}')
   return {'iata':iata,'value':value,'confirmed':True,'target_id':target_id,'role':role,'via':'picker'}
  value=read_value();near=''
  try:near=q.locator('xpath=..').inner_text(timeout=300)
  except Exception:pass
  top=matches[0][2] if matches else ''
  if not chosen(value,top):raise ValueError(f'autocomplete no confirmó {iata}; value={value!r}; nearby={near[:160]!r}')
  try:q.press('Tab')
  except Exception:pass
  return {'iata':iata,'value':value,'confirmed':True,'target_id':target_id,'role':role,'via':how}
 @staticmethod
 def _date_formats(placeholder,typ):
  p=(placeholder or '').lower()
  if typ=='date':return ['%Y-%m-%d']
  if re.search(r'y{2,4}.*m{2}.*d{2}|a{2,4}.*m{2}.*d{2}',p):return ['%Y-%m-%d']
  if re.search(r'm{2}.*d{2}',p) and p.find('mm')<p.find('dd'):return ['%m/%d/%Y']
  return ['%d/%m/%Y','%m/%d/%Y','%d-%m-%Y']
 def fill_date(self,target_id,iso,role=None):
  if not isinstance(target_id,int) or not iso:raise ValueError('fill_date requiere target_id entero e iso (YYYY-MM-DD)')
  d=date.fromisoformat(str(iso)[:10]);q,fr=self._loc(target_id)
  typ=(q.get_attribute('type') or '').lower();ph=q.get_attribute('placeholder') or '';readonly=q.get_attribute('readonly') is not None or q.get_attribute('aria-readonly')=='true'
  def read():
   try:return q.input_value().strip()
   except Exception:
    try:return (q.inner_text(timeout=300) or '').strip()
    except Exception:return ''
  if typ=='date':
   q.fill(d.isoformat());self.page.wait_for_timeout(300)
   if date_matches(read(),d):return {'iso':d.isoformat(),'value':read(),'via':'native','confirmed':True}
  tag=q.evaluate('(e)=>e.tagName.toLowerCase()')
  if tag in ('input','textarea') and not readonly and typ!='date':
   for fmt in self._date_formats(ph,typ)[:2]:
    try:
     q.click();q.press('ControlOrMeta+A');q.press('Backspace');q.type(d.strftime(fmt),delay=25);q.press('Tab');self.page.wait_for_timeout(400)
    except Exception:break
    if date_matches(read(),d):return {'iso':d.isoformat(),'value':read(),'via':'typed:'+fmt,'confirmed':True}
  # calendario (se navega mes a mes; el disparador puede ser un botón de rango "Depart - Return")
  trig=' '.join(filter(None,[q.get_attribute('aria-label'),(q.inner_text(timeout=500) if tag!='input' else '')]));rng=bool(re.search(r'return|regreso|vuelta',trig,re.I) and re.search(r'depart|salida|ida\b',trig,re.I))
  try:is_open=bool(self.page.evaluate(CAL_OPEN_JS))
  except Exception:is_open=False
  if not is_open:
   try:q.click(timeout=3000)
   except Exception as e:
    if 'intercepts pointer events' in str(e):raise ValueError('click bloqueado por overlay/modal; resolver modal visible antes de continuar')
   self.page.wait_for_timeout(400)
  if not self._pick_day(d):raise ValueError(f'fecha {d.isoformat()} no encontrada navegando el calendario mes a mes')
  self.page.wait_for_timeout(400)
  sel=False
  try:
   sd=self.page.locator('[data-fw-day="1"]')
   if sd.count():sel=bool(sd.first.evaluate(SEL_JS,timeout=800))
  except Exception:sel=False
  is_return=(role or '').startswith('return')
  if not rng or is_return:  # en un rango, "Done" sólo después de elegir la vuelta
   done=self.page.get_by_role('button',name=re.compile(r'^(done|apply|ok|aplicar|listo|confirmar|aceptar|select|seleccionar)$',re.I))
   if done.count():
    try:done.first.click(timeout=1500);self.page.wait_for_timeout(500)
    except Exception:pass
  v=read()
  if date_matches(v,d) or (not v and date_matches(self._near(q),d)):return {'iso':d.isoformat(),'value':v,'via':'calendar','confirmed':True}
  if sel:return {'iso':d.isoformat(),'value':v,'via':'calendar:selected','confirmed':True}
  if rng and not is_return:return {'iso':d.isoformat(),'value':v,'via':'calendar:range-open','confirmed':True,'verified':False}  # la validación final en resultados comprueba las fechas
  raise ValueError(f'fecha {d.isoformat()} no confirmada; value={v!r}')
 def _near(self,q):
  try:return q.locator('xpath=..').inner_text(timeout=300)
  except Exception:return ''
 def _pick_day(self,d,max_months=30):
  pats=date_patterns(d)
  for _ in range(max_months):
   try:r=self.page.evaluate(PICK_DAY_JS,{'patterns':pats,'iso':d.isoformat()})
   except Exception:r={'found':False}
   if r.get('found'):
    try:self.page.locator('[data-fw-day="1"]').first.click(timeout=3000);return True
    except Exception:return False
   try:has=self.page.evaluate(NEXT_MONTH_JS)
   except Exception:has=False
   if not has:return False
   try:self.page.locator('[data-fw-next="1"]').first.click(timeout=2000)
   except Exception:return False
   self.page.wait_for_timeout(150)
  return False
 def select_option(self,target_id,value):
  q,fr=self._loc(target_id);tag=q.evaluate('(e)=>e.tagName.toLowerCase()')
  if tag!='select':raise ValueError(f'select requiere <select>; target {target_id} es {tag}')
  try:q.select_option(label=str(value))
  except Exception:
   opts=q.evaluate('(e)=>[...e.options].map(o=>({v:o.value,t:(o.text||"").trim()}))');m=[o for o in opts if str(value).lower() in o['t'].lower() or str(value)==o['v']]
   if not m:raise ValueError(f'opción {value!r} no existe en select {target_id}')
   q.select_option(value=m[0]['v'])
  return {'value':q.evaluate('(e)=>e.options[e.selectedIndex].text')}
 # ------------------------------------------------------------------ acciones
 def act(self,a):
  action=a.get('action');target=a.get('target_id')
  if action not in ALLOWED:raise ValueError(f'Acción no permitida: {action}')
  if action in ('finish','fail'):return
  if action=='back':
   r=self.page.go_back(wait_until='domcontentloaded',timeout=30000)
   if r is None or self.page.url in ('about:blank',''):self.page.goto(self.start_url,wait_until='domcontentloaded',timeout=60000)
   return
  if action=='restart':self.page.goto(self.start_url,wait_until='domcontentloaded',timeout=60000);return
  if action=='wait':self.page.wait_for_timeout(min(10000,max(250,int(a.get('ms',1000)))));return
  if action=='fill_airport':return self.fill_airport(target,a.get('iata') or a.get('value'),a.get('role'))
  if action=='fill_date':return self.fill_date(target,a.get('iso') or a.get('value'),a.get('role'))
  if action=='select':return self.select_option(target,a.get('value'))
  q,fr=self._loc(target)
  if action in ('check','uncheck'):  # idempotente: switches/checkbox de React suelen tener el input tapado por su label
   want=action=='check'
   try:q.set_checked(want,force=True,timeout=3000)
   except Exception:
    if q.evaluate('e=>!!e.checked')!=want:q.evaluate('e=>e.click()')
   self.page.wait_for_timeout(300)
   if q.evaluate('e=>!!e.checked')!=want:raise ValueError(f'no se pudo {action} el control {target}')
   return {'checked':want}
  if action=='click':
   try:q.click(timeout=3500)
   except Exception as e:
    if 'not visible' in str(e):raise ValueError(f'target_id {target} dejó de estar visible; reobservar')
    if 'intercepts pointer events' in str(e):raise ValueError('click bloqueado por overlay/modal; resolver modal visible antes de continuar')
    raise
  elif action=='fill':
   if not a.get('value'):raise ValueError('fill requiere value no vacío')
   q.fill(str(a['value']));self.page.wait_for_timeout(500)
  elif action=='press':q.press(str(a.get('key','Enter')))
