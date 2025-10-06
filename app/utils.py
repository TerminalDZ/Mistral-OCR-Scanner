# app/utils.py
import os
import sqlite3
import uuid
from pathlib import Path
from datetime import datetime
from dotenv import load_dotenv
import json

load_dotenv()

BASE = Path(os.environ.get("STORAGE_PATH", "./data"))
UPLOADS = BASE / "uploads"
RESULTS = BASE / "results"
DB_PATH = BASE / "jobs.db"

# ensure dirs
BASE.mkdir(parents=True, exist_ok=True)
UPLOADS.mkdir(parents=True, exist_ok=True)
RESULTS.mkdir(parents=True, exist_ok=True)

def new_job_id():
    return uuid.uuid4().hex

def save_upload_file(upload_file):
    """
    Save a Starlette UploadFile to disk. Returns (file_path, job_id, original_filename).
    """
    job_id = new_job_id()
    original_name = upload_file.filename
    safe_name = f"{job_id}_{original_name}"
    dest = UPLOADS / safe_name
    with open(dest, "wb") as f:
        while True:
            chunk = upload_file.file.read(1024 * 1024)
            if not chunk:
                break
            f.write(chunk)
    return str(dest), job_id, original_name

def result_path(job_id: str):
    return str(RESULTS / f"{job_id}.json")

# ---------- SQLite helpers ----------
def get_db_conn():
    conn = sqlite3.connect(str(DB_PATH), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn

def _table_columns(conn, table_name):
    cur = conn.execute(f"PRAGMA table_info({table_name})")
    return [row["name"] for row in cur.fetchall()]

def init_db():
    """
    Initialize DB and perform simple migrations.
    Ensures table 'jobs' exists with expected columns; if columns are missing, ALTER TABLE ADD COLUMN.
    """
    conn = get_db_conn()
    try:
        cur = conn.cursor()
        # If table doesn't exist, create complete schema
        cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='jobs'")
        row = cur.fetchone()
        if not row:
            cur.execute("""
            CREATE TABLE jobs (
              job_id TEXT PRIMARY KEY,
              title TEXT,
              filename TEXT,
              filepath TEXT,
              resultpath TEXT,
              status TEXT,
              created_at TEXT,
              completed_at TEXT,
              pages INTEGER,
              size_bytes INTEGER,
              extra TEXT
            )
            """)
            conn.commit()
            return

        # If table exists, check columns and add missing ones
        existing = _table_columns(conn, "jobs")
        required = {
            "job_id": "TEXT PRIMARY KEY",
            "title": "TEXT",
            "filename": "TEXT",
            "filepath": "TEXT",
            "resultpath": "TEXT",
            "status": "TEXT",
            "created_at": "TEXT",
            "completed_at": "TEXT",
            "pages": "INTEGER",
            "size_bytes": "INTEGER",
            "extra": "TEXT"
        }
        for col, coltype in required.items():
            if col not in existing:
                cur.execute(f"ALTER TABLE jobs ADD COLUMN {col} {coltype}")
                conn.commit()
    finally:
        conn.close()

def insert_job(job_id, title, filename, filepath, size_bytes):
    conn = get_db_conn()
    with conn:
        conn.execute("""
        INSERT INTO jobs(job_id, title, filename, filepath, resultpath, status, created_at, pages, size_bytes, extra)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (job_id, title, filename, filepath, None, "pending", datetime.utcnow().isoformat(), None, size_bytes, json.dumps({})))
    conn.close()

def update_job_completed(job_id, resultpath, status="completed", pages=None, title=None):
    conn = get_db_conn()
    with conn:
        if title is not None:
            conn.execute("""
            UPDATE jobs SET resultpath = ?, status = ?, completed_at = ?, pages = ?, title = ?
            WHERE job_id = ?
            """, (resultpath, status, datetime.utcnow().isoformat(), pages, title, job_id))
        else:
            conn.execute("""
            UPDATE jobs SET resultpath = ?, status = ?, completed_at = ?, pages = ?
            WHERE job_id = ?
            """, (resultpath, status, datetime.utcnow().isoformat(), pages, job_id))
    conn.close()

def update_job_title(job_id, title):
    conn = get_db_conn()
    with conn:
        conn.execute("UPDATE jobs SET title = ? WHERE job_id = ?", (title, job_id))
    conn.close()

def list_jobs(limit=100):
    conn = get_db_conn()
    cur = conn.cursor()
    cur.execute("SELECT * FROM jobs ORDER BY created_at DESC LIMIT ?", (limit,))
    rows = cur.fetchall()
    conn.close()
    return [dict(r) for r in rows]

def get_job(job_id):
    conn = get_db_conn()
    cur = conn.cursor()
    cur.execute("SELECT * FROM jobs WHERE job_id = ?", (job_id,))
    row = cur.fetchone()
    conn.close()
    return dict(row) if row else None
