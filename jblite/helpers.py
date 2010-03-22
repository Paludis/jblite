import sqlite3

def with_db(db_fname, fn, *args, **kwargs):
    """Wrapper for a full self-contained SQLite database transaction."""
    conn = sqlite3.connect(db_fname)
    cur = conn.cursor()
    try:
        fn(cur, *args, **kwargs)
        conn.commit()
    finally:
        cur.close()
        conn.close()
