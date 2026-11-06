"""Local feedback storage, kept separate from training data."""
import os
from pathlib import Path
from contextlib import closing
import sqlite3

DATA_DIR = Path(os.environ.get('DATA_DIR', Path(__file__).parent / 'data'))
DB = DATA_DIR / 'feedback.sqlite3'

def save_feedback(message, rating, category, model):
    if not isinstance(message,str) or not 5<=len(message.strip())<=2000:
        raise ValueError('Please write between 5 and 2,000 characters.')
    if type(rating) is not int or not 1<=rating<=5:
        raise ValueError('Choose a rating from 1 to 5.')
    if category not in ('answer', 'bug', 'idea', 'other'):
        raise ValueError('Choose a feedback category.')
    DB.parent.mkdir(parents=True,exist_ok=True)
    with closing(sqlite3.connect(DB,timeout=5)) as connection, connection:
        connection.execute("CREATE TABLE IF NOT EXISTS feedback (id INTEGER PRIMARY KEY, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, message TEXT NOT NULL, rating INTEGER NOT NULL, category TEXT NOT NULL, model TEXT NOT NULL)")
        result=connection.execute('INSERT INTO feedback (message,rating,category,model) VALUES (?,?,?,?)',
                                 (message.strip(),rating,category,model))
        return result.lastrowid
