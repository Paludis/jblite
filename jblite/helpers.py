# -*- coding:utf-8 -*-
import time, sqlite3, gzip


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


def do_time(fn, *args, **kwargs):
    """Wraps a function call and prints the result.

    Technically, this will also wrap an object instantiation, and will
    return the object.  (This lets us time ElementTree instantiation.)

    """
    start = time.time()
    result = fn(*args, **kwargs)
    end = time.time()
    print("do_time: Fn=%s, Time=%f" % (repr(fn), end-start))
    return result
