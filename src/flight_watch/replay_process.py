from __future__ import annotations
import argparse,time
from datetime import date
from .domain import SearchRequest
from .providers import AlmundoProvider,AerolineasProvider
PROVIDERS={'almundo':AlmundoProvider,'aerolineas':AerolineasProvider}
def main():
 ap=argparse.ArgumentParser();ap.add_argument('--profile-id',default='');ap.add_argument('--provider',choices=PROVIDERS,default='almundo');ap.add_argument('--origin',required=True);ap.add_argument('--destination',required=True);ap.add_argument('--departure',required=True);ap.add_argument('--return-date',required=True);ap.add_argument('--age',type=int,default=30);ap.add_argument('--max-stops',type=int,default=2);a=ap.parse_args()
 r=SearchRequest(a.origin,a.destination,date.fromisoformat(a.departure),date.fromisoformat(a.return_date),(a.age,),max_stops=a.max_stops)
 provider=PROVIDERS[a.provider]();pw,ctx,page=provider.replay(r,profile_id=a.profile_id)
 print(f'Replay {a.provider}: {page.url}',flush=True)
 try:
  # Keep Playwright alive until user closes every page/window.
  while ctx.pages:time.sleep(.5)
 finally:
  try:ctx.close()
  except Exception:pass
  try:pw.stop()
  except Exception:pass
if __name__=='__main__':main()
