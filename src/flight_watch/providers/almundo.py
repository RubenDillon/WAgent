import re
from datetime import datetime
from urllib.parse import urlencode
from ..browser import BrowserSession
from ..domain import Observation
BASE="https://almundo.com.ar/flights/results"
def build_url(r):
 a,c,b=r.counts()
 if b:raise ValueError("Bebes aun no soportados de forma verificable")
 return BASE+"?"+urlencode({"from":f"{r.origin},{r.destination}","to":f"{r.destination},{r.origin}","date":f"{r.departure},{r.return_date}","adults":a,"children":c,"currencyCode":"USD"})+"#sortBy=PRICE"
def price(s):
 m=re.search(r"(?:u\$s|us\$|usd)\s*([\d.,]+)",s,re.I)
 if not m:return None
 x=m.group(1);x=x.replace(".","").replace(",",".") if "," in x else x.replace(".","")
 try:return float(x)
 except:return None
def stops(s):
 if re.search(r"\bDirecto\b",s,re.I):return 0
 m=re.search(r"(\d+)\s+Escalas?",s,re.I);return int(m.group(1)) if m else None
class AlmundoProvider:
 name='almundo'
 def search(self,r,visible=False):
  batch=datetime.now().strftime("%Y%m%d%H%M%S%f")
  with BrowserSession("almundo",visible) as b:
   p=b.page;p.goto(build_url(r),wait_until="domcontentloaded",timeout=60000);p.locator("am-cluster-container").first.wait_for(state="attached",timeout=45000);raw=p.locator("am-cluster-container").evaluate_all("els=>els.map(c=>({price:(c.querySelector('.pricebox')||{}).innerText||'',text:c.innerText||'',logos:[...c.querySelectorAll('img[alt=airline_logo]')].map(i=>(i.src.split('/').pop()||'').split('-')[0])}))")
   out=[]
   for x in raw:
    v=price(x["price"]);st=stops(x["text"])
    if v is not None and (st is None or st<=r.max_stops):out.append(Observation("almundo",r,v,"USD",datetime.now(),p.url,",".join(dict.fromkeys(x["logos"])),st,x["text"][:800],batch))
   return sorted(out,key=lambda z:z.price)
 def replay(self,r,profile_id=''):
  from playwright.sync_api import sync_playwright
  import uuid
  pid=profile_id or uuid.uuid4().hex
  pw=sync_playwright().start();p=__import__('pathlib').Path(__file__).resolve().parents[3]/"data"/"browser"/"replays"/pid;p.mkdir(parents=True,exist_ok=True)
  ctx=pw.chromium.launch_persistent_context(str(p),headless=False);page=ctx.pages[0] if ctx.pages else ctx.new_page();page.goto(build_url(r));return pw,ctx,page

