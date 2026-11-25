from pathlib import Path
from playwright.sync_api import sync_playwright
BASE=Path(__file__).resolve().parents[2]
class BrowserSession:
 def __init__(self,name,visible=False):self.name=name;self.visible=visible
 def __enter__(self):
  self.pw=sync_playwright().start();p=BASE/"data"/"browser"/self.name;p.mkdir(parents=True,exist_ok=True);self.ctx=self.pw.chromium.launch_persistent_context(str(p),headless=not self.visible,locale="es-AR",viewport={"width":1400,"height":1000});self.page=self.ctx.pages[0] if self.ctx.pages else self.ctx.new_page();return self
 def __exit__(self,*_):self.ctx.close();self.pw.stop()
