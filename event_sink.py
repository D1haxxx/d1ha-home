"""Anonymous local event queue shared with the owner's notification bot."""
import os
from pathlib import Path
from contextlib import closing
import sqlite3,hashlib
DATA_DIR = Path(os.environ.get('DATA_DIR', Path(__file__).parent / 'data'))
DB = DATA_DIR / 'app_events.sqlite3'
KINDS={'website_visit','bot_visit','app_error'}

def connect():
 DB.parent.mkdir(parents=True,exist_ok=True);db=sqlite3.connect(DB,timeout=5)
 db.executescript('CREATE TABLE IF NOT EXISTS visitors (kind TEXT NOT NULL, key TEXT NOT NULL, PRIMARY KEY(kind,key)); CREATE TABLE IF NOT EXISTS events (id INTEGER PRIMARY KEY, kind TEXT NOT NULL, detail TEXT NOT NULL, created TEXT DEFAULT CURRENT_TIMESTAMP);')
 return db

def record(kind,detail):
 if kind not in KINDS:raise ValueError('Unknown event')
 with closing(connect()) as db,db:db.execute('INSERT INTO events(kind,detail) VALUES (?,?)',(kind,detail[:100]))

def visitor(kind,identifier):
 if kind not in ('website_visit','bot_visit'):raise ValueError('Unknown visitor kind')
 digest=hashlib.sha256(str(identifier).encode()).hexdigest()
 with closing(connect()) as db,db:
  result=db.execute('INSERT OR IGNORE INTO visitors VALUES (?,?)',(kind,digest))
  if result.rowcount:db.execute('INSERT INTO events(kind,detail) VALUES (?,?)',(kind,'First visit in this browser' if kind=='website_visit' else 'First start of the notification bot'))

def safe_record(kind,detail):
 try:record(kind,detail)
 except (OSError,sqlite3.Error):pass
