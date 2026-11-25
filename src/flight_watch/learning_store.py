from __future__ import annotations
import json,sqlite3
from datetime import datetime
from .database import DB,conn
TERMINAL=('COMPLETED','FAILED','CANCELLED_BY_USER','INTERRUPTED')
def ensure():
 with conn() as c:
  c.executescript('''
  CREATE TABLE IF NOT EXISTS system_settings(key TEXT PRIMARY KEY,value TEXT NOT NULL,updated_at TEXT NOT NULL);
  CREATE TABLE IF NOT EXISTS learning_jobs(id INTEGER PRIMARY KEY AUTOINCREMENT,provider TEXT NOT NULL,start_url TEXT,job_type TEXT NOT NULL CHECK(job_type IN ('LEARN','REPAIR')),priority INTEGER NOT NULL,status TEXT NOT NULL,created_at TEXT NOT NULL,started_at TEXT,finished_at TEXT,cancel_requested_at TEXT,progress INTEGER DEFAULT 0,max_actions INTEGER DEFAULT 40,current_action TEXT,goal_json TEXT,checkpoint_json TEXT,last_error TEXT);
  CREATE TABLE IF NOT EXISTS learning_events(id INTEGER PRIMARY KEY AUTOINCREMENT,job_id INTEGER NOT NULL,created_at TEXT NOT NULL,level TEXT NOT NULL,message TEXT NOT NULL,FOREIGN KEY(job_id) REFERENCES learning_jobs(id));
  CREATE INDEX IF NOT EXISTS ix_learning_queue ON learning_jobs(status,priority DESC,created_at);
  ''')
  c.execute("INSERT OR IGNORE INTO system_settings(key,value,updated_at) VALUES('intelligent_worker_enabled','0',?)",(datetime.now().isoformat(),))
def enabled():
 ensure()
 with conn() as c:return c.execute("SELECT value FROM system_settings WHERE key='intelligent_worker_enabled'").fetchone()[0]=='1'
def set_enabled(value):
 ensure()
 with conn() as c:c.execute("INSERT INTO system_settings(key,value,updated_at) VALUES('intelligent_worker_enabled',?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value,updated_at=excluded.updated_at",('1' if value else '0',datetime.now().isoformat()))
def enqueue(provider,url,job_type,goal,priority=None):
 ensure();priority=priority if priority is not None else (100 if job_type=='REPAIR' else 80)
 with conn() as c:
  cur=c.execute("INSERT INTO learning_jobs(provider,start_url,job_type,priority,status,created_at,goal_json,current_action) VALUES(?,?,?,?,?,?,?,?)",(provider,url,job_type,priority,'QUEUED',datetime.now().isoformat(),json.dumps(goal,ensure_ascii=False),'En cola'));jid=cur.lastrowid
  c.execute("INSERT INTO learning_events(job_id,created_at,level,message) VALUES(?,?,?,?)",(jid,datetime.now().isoformat(),'INFO','Trabajo encolado'))
 return jid
def list_jobs(limit=100):
 ensure()
 with conn() as c:return [dict(x) for x in c.execute("SELECT * FROM learning_jobs ORDER BY CASE WHEN status='RUNNING' THEN 0 WHEN status='QUEUED' THEN 1 ELSE 2 END,priority DESC,created_at DESC LIMIT ?",(limit,))]
def active():
 ensure()
 with conn() as c:
  r=c.execute("SELECT * FROM learning_jobs WHERE status='RUNNING' ORDER BY started_at LIMIT 1").fetchone();return dict(r) if r else None
def request_cancel(job_id):
 with conn() as c:c.execute("UPDATE learning_jobs SET cancel_requested_at=?,current_action='Detención solicitada' WHERE id=? AND status='RUNNING'",(datetime.now().isoformat(),job_id))
def cancel_queued(job_id):
 with conn() as c:c.execute("UPDATE learning_jobs SET status='CANCELLED_BY_USER',finished_at=?,current_action='Cancelado antes de iniciar' WHERE id=? AND status='QUEUED'",(datetime.now().isoformat(),job_id))
def claim_next():
 ensure()
 if not enabled():return None
 c=sqlite3.connect(DB,timeout=30,isolation_level=None);c.row_factory=sqlite3.Row
 try:
  c.execute('BEGIN IMMEDIATE')
  if c.execute("SELECT 1 FROM learning_jobs WHERE status='RUNNING' LIMIT 1").fetchone():c.execute('ROLLBACK');return None
  r=c.execute("SELECT * FROM learning_jobs WHERE status='QUEUED' ORDER BY priority DESC,created_at LIMIT 1").fetchone()
  if not r:c.execute('ROLLBACK');return None
  now=datetime.now().isoformat();c.execute("UPDATE learning_jobs SET status='RUNNING',started_at=?,current_action='Preparando worker' WHERE id=? AND status='QUEUED'",(now,r['id']));c.execute('COMMIT');return dict(r)
 except Exception:
  try:c.execute('ROLLBACK')
  except Exception:pass
  raise
 finally:c.close()
def update(job_id,progress,action,checkpoint=None):
 with conn() as c:c.execute("UPDATE learning_jobs SET progress=?,current_action=?,checkpoint_json=? WHERE id=?",(progress,action,json.dumps(checkpoint or {}),job_id))
def cancellation_requested(job_id):
 with conn() as c:
  r=c.execute("SELECT cancel_requested_at FROM learning_jobs WHERE id=?",(job_id,)).fetchone();return bool(r and r[0])
def finish(job_id,status,error=None):
 with conn() as c:c.execute("UPDATE learning_jobs SET status=?,finished_at=?,current_action=?,last_error=? WHERE id=?",(status,datetime.now().isoformat(),status,error,job_id))


def add_event(job_id,level,message):
 ensure()
 with conn() as c:c.execute("INSERT INTO learning_events(job_id,created_at,level,message) VALUES(?,?,?,?)",(job_id,datetime.now().isoformat(),level,message))
def events(job_id,limit=500):
 ensure()
 with conn() as c:return [dict(x) for x in c.execute("SELECT * FROM learning_events WHERE job_id=? ORDER BY id DESC LIMIT ?",(job_id,limit))][::-1]
def recover_interrupted():
 ensure()
 with conn() as c:c.execute("UPDATE learning_jobs SET status='INTERRUPTED',finished_at=?,current_action='Worker anterior interrumpido' WHERE status='RUNNING'",(datetime.now().isoformat(),))
def enqueue_repair_if_missing(provider,url,goal,reason):
 ensure()
 with conn() as c:
  r=c.execute("SELECT id FROM learning_jobs WHERE provider=? AND job_type='REPAIR' AND status IN ('QUEUED','RUNNING')",(provider,)).fetchone()
  if r:return r[0]
 jid=enqueue(provider,url,'REPAIR',goal,100);add_event(jid,'WARN','Reparación automática: '+reason);return jid


def delete_job(job_id):
 ensure()
 with conn() as c:
  r=c.execute("SELECT status FROM learning_jobs WHERE id=?",(job_id,)).fetchone()
  if not r:return False,'Trabajo inexistente'
  if r[0]=='RUNNING':return False,'No se puede borrar un trabajo RUNNING; primero detenelo.'
  c.execute("DELETE FROM learning_events WHERE job_id=?",(job_id,))
  c.execute("DELETE FROM learning_jobs WHERE id=?",(job_id,))
  return True,'Trabajo eliminado'
def clear_finished():
 ensure()
 with conn() as c:
  ids=[x[0] for x in c.execute("SELECT id FROM learning_jobs WHERE status IN ('COMPLETED','FAILED','CANCELLED_BY_USER','INTERRUPTED')")]
  for jid in ids:c.execute("DELETE FROM learning_events WHERE job_id=?",(jid,))
  if ids:c.execute("DELETE FROM learning_jobs WHERE status IN ('COMPLETED','FAILED','CANCELLED_BY_USER','INTERRUPTED')")
  return len(ids)


def recover_stale_running(max_age_seconds=30):
 ensure()
 now=datetime.now()
 fixed=[]
 with conn() as c:
  rows=c.execute("SELECT id,started_at FROM learning_jobs WHERE status='RUNNING'").fetchall()
  for r in rows:
   try:started=datetime.fromisoformat(r['started_at']) if r['started_at'] else now
   except Exception:started=now
   if (now-started).total_seconds()>=max_age_seconds:
    c.execute("UPDATE learning_jobs SET status='INTERRUPTED',finished_at=?,current_action='RUNNING huérfano recuperado al reiniciar worker',last_error='El worker anterior no estaba procesando este job.' WHERE id=?",(now.isoformat(),r['id']));fixed.append(r['id'])
 return fixed


def queue_diagnostics():
 ensure()
 with conn() as c:
  enabled_row=c.execute("SELECT value FROM system_settings WHERE key='intelligent_worker_enabled'").fetchone()
  running=[dict(x) for x in c.execute("SELECT id,provider,job_type,status,started_at,current_action FROM learning_jobs WHERE status='RUNNING' ORDER BY started_at")]
  queued=[dict(x) for x in c.execute("SELECT id,provider,job_type,status,priority,created_at,current_action FROM learning_jobs WHERE status='QUEUED' ORDER BY priority DESC,created_at")]
 return {'enabled':bool(enabled_row and enabled_row[0]=='1'),'running':running,'queued':queued}
def interrupt_all_running(reason='Worker reiniciado por usuario'):
 ensure();now=datetime.now().isoformat()
 with conn() as c:
  rows=c.execute("SELECT id FROM learning_jobs WHERE status='RUNNING'").fetchall()
  for r in rows:
   c.execute("UPDATE learning_jobs SET status='INTERRUPTED',finished_at=?,current_action=?,last_error=? WHERE id=?",(now,reason,reason,r['id']))
 return len(rows)


def purge_learning_queue(include_running=False):
 ensure()
 with conn() as c:
  statuses=['QUEUED','COMPLETED','FAILED','CANCELLED_BY_USER','INTERRUPTED']
  if include_running:statuses.append('RUNNING')
  marks=','.join('?' for _ in statuses)
  ids=[x[0] for x in c.execute(f"SELECT id FROM learning_jobs WHERE status IN ({marks})",statuses)]
  for jid in ids:c.execute("DELETE FROM learning_events WHERE job_id=?",(jid,))
  if ids:c.execute(f"DELETE FROM learning_jobs WHERE status IN ({marks})",statuses)
  return len(ids)
def reset_learning_system():
 ensure();now=datetime.now().isoformat()
 with conn() as c:
  c.execute("UPDATE learning_jobs SET status='INTERRUPTED',finished_at=?,current_action='Reset manual del learning worker',last_error='Reset manual' WHERE status='RUNNING'",(now,))
 return purge_learning_queue(include_running=True)
