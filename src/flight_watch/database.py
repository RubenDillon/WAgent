import sqlite3,statistics,math
from pathlib import Path
from datetime import datetime
DB=Path(__file__).resolve().parents[2]/'data'/'flight_watch.db'
SCHEMA="""CREATE TABLE IF NOT EXISTS observations(id INTEGER PRIMARY KEY,provider TEXT,request_json TEXT,route_key TEXT,price REAL,currency TEXT,observed_at TEXT,url TEXT,airline TEXT,stops INTEGER,details TEXT,batch_id TEXT);CREATE INDEX IF NOT EXISTS ix_route ON observations(route_key,observed_at);"""
MIGRATIONS={'url':"TEXT DEFAULT ''",'airline':"TEXT DEFAULT ''",'stops':'INTEGER','details':"TEXT DEFAULT ''",'batch_id':"TEXT DEFAULT ''"}
def conn(path=DB):
 path.parent.mkdir(parents=True,exist_ok=True);c=sqlite3.connect(path);c.row_factory=sqlite3.Row;c.executescript(SCHEMA);cols={r[1] for r in c.execute('PRAGMA table_info(observations)')}
 for name,definition in MIGRATIONS.items():
  if name not in cols:c.execute(f'ALTER TABLE observations ADD COLUMN {name} {definition}')
 c.commit();return c
def migrate(path=DB):
 c=conn(path);cols=[r[1] for r in c.execute('PRAGMA table_info(observations)')];c.close();return cols
def key(r):return f'{r.origin}-{r.destination}:{r.departure}:{r.return_date}:{r.cabin}'
def insert(o,path=DB):
 with conn(path) as c:return c.execute('INSERT INTO observations(provider,request_json,route_key,price,currency,observed_at,url,airline,stops,details,batch_id) VALUES(?,?,?,?,?,?,?,?,?,?,?)',(o.provider,o.request.to_json(),key(o.request),o.price,o.currency,o.observed_at.isoformat(),o.url,o.airline,o.stops,o.details,o.batch_id)).lastrowid
def cycle_rows(r,path=DB):
 with conn(path) as c:return [dict(x) for x in c.execute("SELECT MIN(price) price,MIN(observed_at) observed_at,provider,currency FROM observations WHERE route_key=? GROUP BY COALESCE(NULLIF(batch_id,''),substr(observed_at,1,16)),provider,currency ORDER BY observed_at",(key(r),))]
def percentile(values,p):
 if not values:return None
 a=sorted(values);k=(len(a)-1)*p;lo=math.floor(k);hi=math.ceil(k)
 return a[lo] if lo==hi else a[lo]+(a[hi]-a[lo])*(k-lo)
def analytics(r,path=DB):
 rows=cycle_rows(r,path);p=[x['price'] for x in rows]
 if not p:return None
 ts=[datetime.fromisoformat(x['observed_at']) for x in rows]
 return {'count':len(p),'minimum':min(p),'p10':percentile(p,.10),'p25':percentile(p,.25),'median':statistics.median(p),'p75':percentile(p,.75),'maximum':max(p),'current':p[-1],'history_days':max(1,(max(ts)-min(ts)).days+1),'rows':rows}
def provider_analytics(r,path=DB):
 rows=cycle_rows(r,path);out={}
 for provider in sorted({x['provider'] for x in rows}):
  rr=[x for x in rows if x['provider']==provider];p=[x['price'] for x in rr]
  out[provider]={'count':len(p),'minimum':min(p),'p10':percentile(p,.10),'p25':percentile(p,.25),'median':statistics.median(p),'p75':percentile(p,.75),'maximum':max(p),'current':p[-1],'rows':rr}
 return out


def ensure_exchange_schema(path=DB):
 with conn(path) as c:
  c.execute("""CREATE TABLE IF NOT EXISTS exchange_rates(rate_date TEXT NOT NULL,currency TEXT NOT NULL,ars_per_unit REAL NOT NULL,rate_type TEXT NOT NULL,source TEXT NOT NULL,retrieved_at TEXT NOT NULL,PRIMARY KEY(rate_date,currency,rate_type))""")
  c.execute("CREATE INDEX IF NOT EXISTS ix_exchange_date ON exchange_rates(rate_date)")

def upsert_exchange_rate(rate_date,currency,ars_per_unit,rate_type,source,retrieved_at,path=DB):
 ensure_exchange_schema(path)
 with conn(path) as c:c.execute("INSERT INTO exchange_rates(rate_date,currency,ars_per_unit,rate_type,source,retrieved_at) VALUES(?,?,?,?,?,?) ON CONFLICT(rate_date,currency,rate_type) DO UPDATE SET ars_per_unit=excluded.ars_per_unit,source=excluded.source,retrieved_at=excluded.retrieved_at",(rate_date,currency,ars_per_unit,rate_type,source,retrieved_at))

def exchange_rate(rate_date,currency='USD',rate_type='BCRA_USD_COTIZACION',path=DB):
 ensure_exchange_schema(path)
 with conn(path) as c:
  r=c.execute("SELECT * FROM exchange_rates WHERE rate_date=? AND currency=? AND rate_type=?",(rate_date,currency,rate_type)).fetchone()
  return dict(r) if r else None

def latest_exchange_rate(currency='USD',rate_type='BCRA_USD_COTIZACION',path=DB):
 ensure_exchange_schema(path)
 with conn(path) as c:
  r=c.execute("SELECT * FROM exchange_rates WHERE currency=? AND rate_type=? ORDER BY rate_date DESC LIMIT 1",(currency,rate_type)).fetchone()
  return dict(r) if r else None

def exchange_history(currency='USD',rate_type='BCRA_USD_COTIZACION',path=DB):
 ensure_exchange_schema(path)
 with conn(path) as c:return [dict(x) for x in c.execute("SELECT * FROM exchange_rates WHERE currency=? AND rate_type=? ORDER BY rate_date",(currency,rate_type))]
