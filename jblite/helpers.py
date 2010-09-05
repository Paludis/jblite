import sqlite3, gzip


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


def gzread(fname):
    try:
        infile = gzip.open(fname)
        data = infile.read()
        infile.close()
    except IOError, e:
        if e.args[0] == "Not a gzipped file":
            with open(fname) as infile:
                data = infile.read()
        else:
            raise e
    return data

