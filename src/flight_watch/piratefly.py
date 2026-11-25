from pathlib import Path
from datetime import datetime,timedelta
import json,requests
BASE=Path(__file__).resolve().parents[2];CACHE=BASE/'data'/'cache'/'piratefly.json'
API='https://piratefly.com/v1/analisi'
CITY={'EZE':'Buenos Aires','AEP':'Buenos Aires','MAD':'Madrid','FCO':'Rome','CIA':'Rome','CDG':'Paris','ORY':'Paris','LHR':'London','LGW':'London','STN':'London','LTN':'London','JFK':'New York','EWR':'New York','LGA':'New York'}
def city(code):return CITY.get(code.upper(),code.upper())
def verdict(origin,destination,refresh=False):
 CACHE.parent.mkdir(parents=True,exist_ok=True);o,d=city(origin),city(destination);key=f'{o}->{d}'
 if CACHE.exists() and not refresh:
  try:
   all=json.loads(CACHE.read_text());x=all.get(key)
   if x and datetime.fromisoformat(x['cached_at'])>datetime.now()-timedelta(hours=12):return x['data']
  except Exception:pass
 r=requests.get(API,params={'origine':o,'destinazione':d},headers={'Accept':'application/json','User-Agent':'FlightWatchAgent/0.7.3.post2'},timeout=30)
 if r.status_code==404:return {'_status':'NO_COVERAGE','origine':o,'destinazione':d,'_message':f'Piratefly no publica histórico para {o} -> {d} (HTTP 404).'}
 r.raise_for_status();data=r.json();all={}
 if CACHE.exists():
  try:all=json.loads(CACHE.read_text())
  except Exception:pass
 all[key]={'cached_at':datetime.now().isoformat(),'data':data};CACHE.write_text(json.dumps(all,ensure_ascii=False,indent=2));return data
def cents(v):return None if v is None else float(v)/100
