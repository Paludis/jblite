#!/usr/bin/env python

import os, sys, sqlite3
from jbparse import kanjidic2

def drop_kanji_tables(cur):
    tables = (
        "misc",
        "codepoints",
        "radicals",
        "variants",
        "dict_codes",
        "radical_names",
        "nanori",
        "misstrokes",
        "query_codes",
        "senses",
        "readings",
        "meanings",
        )
    for tbl in tables:
        cur.execute("DROP TABLE IF EXISTS %s" % tbl)

def create_kanji_tables(cur):
    """Creates tables for storing kanji information.

    This format should be fully compatible with all data currently
    stored in KANJIDIC2.  (KANJIDIC2 file_version: 4)

    If tables already exist, they will be silently dropped beforehand.

    """
    drop_kanji_tables(cur)
    cur.execute(
        "CREATE TABLE header "
        "(file_version TEXT, database_version TEXT, date_of_creation TEXT)")
    cur.execute(
        "CREATE TABLE misc "
        "(literal TEXT PRIMARY KEY,"
        " grade INTEGER, freq INTEGER, jlpt INTEGER, strokes INTEGER)")
    for tbltype in ("codepoints", "radicals", "variants", "dict_codes"):
        cur.execute(
            "CREATE TABLE %s "
            "(literal TEXT, seq INTEGER, type TEXT, value TEXT,"
            " PRIMARY KEY (literal, seq))" % tbltype)
    for tbltype in ("radical_names", "nanori"):
        cur.execute(
            "CREATE TABLE %s "
            "(literal TEXT, seq INTEGER, value TEXT,"
            " PRIMARY KEY (literal, seq))" % tbltype)
    cur.execute(
        "CREATE TABLE stroke_miscounts "
        "(literal TEXT, seq INTEGER, strokes INTEGER,"
        " PRIMARY KEY (literal, seq))")
    cur.execute(
        "CREATE TABLE query_codes "
        "(literal TEXT, seq INTEGER, type TEXT, value TEXT,"
        " skip_misclass TEXT, PRIMARY KEY (literal, seq))")
    cur.execute(
        "CREATE TABLE readings "
        "(literal TEXT, sense INTEGER, seq INTEGER, type TEXT, value TEXT,"
        " on_type TEXT, status TEXT, PRIMARY KEY (literal, sense, seq))")
    cur.execute(
        "CREATE TABLE meanings "
        "(literal TEXT, sense INTEGER, seq INTEGER, lang TEXT, value TEXT,"
        " PRIMARY KEY (literal, sense, seq))")

def get_data(kd2_fname):
    kd2parser = kanjidic2.Parser(kd2_fname)
    return (kd2parser.header, kd2parser.characters)

def populate_header(cur, header):
    file_version = header.find("file_version").text
    database_version = header.find("database_version").text
    date = header.find("date_of_creation").text
    cur.execute(
        "INSERT INTO header "
        "(file_version, database_version, date_of_creation) VALUES (?, ?, ?)",
        (file_version, database_version, date))

def populate_meanings(cur, kanji, sense, sense_id):
    meanings = sense._get_meaning_nodes()
    if not meanings:
        return
    pairs = []
    for lang in sorted(meanings):
        pairs.extend([(lang, o.text) for o in meanings[lang]])
    pairs = [(kanji.literal, sense_id, i+1, lang, gloss)
             for i, (lang, gloss) in enumerate(pairs)]
    cur.executemany(
        "INSERT INTO meanings (literal, sense, seq, lang, value) "
        "VALUES (?, ?, ?, ?, ?)", pairs)

def populate_readings(cur, kanji, sense, sense_id):
    readings = sense._get_reading_nodes()
    if not readings:
        return
    pairs = []
    for r_type in sorted(readings):
        pairs.extend(
            [(r_type, o.text, o.attrib.get("on_type"), o.attrib.get("r_status"))
             for o in readings[r_type]])
    pairs = [(kanji.literal, sense_id, i+1, r_type, reading, on_type, status)
             for i, (r_type, reading, on_type, status) in enumerate(pairs)]
    cur.executemany(
        "INSERT INTO readings "
        "(literal, sense, seq, type, value, on_type, status) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)", pairs)

def populate_senses(cur, kanji):
    senses = kanji._get_sense_nodes()
    if not senses:
        return
    for i, sense in enumerate(senses):
        i += 1
        populate_readings(cur, kanji, sense, i)
        populate_meanings(cur, kanji, sense, i)

def populate_stroke_miscounts(cur, kanji, miscounts):
    data = [(kanji.literal, i+1, count) for i, count in enumerate(miscounts)]
    cur.executemany(
        "INSERT INTO stroke_miscounts (literal, seq, strokes) "
        "VALUES (?, ?, ?)", data)

def populate_misc(cur, kanji):
    strokes, miscounts = kanji.get_strokes()
    grade = kanji.get_grade()
    freq = kanji.get_freq()
    jlpt = kanji.get_jlpt()
    cur.execute(
        "INSERT INTO misc (literal, grade, freq, jlpt, strokes) "
        "VALUES (?, ?, ?, ?, ?)", (kanji.literal, grade, freq, jlpt, strokes))
    if miscounts:
        populate_stroke_miscounts(cur, kanji, miscounts)

def _populate_val_table(cur, kanji, table_name, nodes):
    if not nodes:
        return
    data = [(kanji.literal, i+1, node.text) for i, node in enumerate(nodes)]
    cur.executemany(
        "INSERT INTO %s (literal, seq, value) VALUES (?, ?, ?)" % table_name,
        data)

def _populate_type_val_table(cur, kanji, table_name, node_d):
    if not node_d:
        return

    data = []
    for typ in sorted(node_d):
        data.extend([(typ, o.text) for o in node_d[typ]])
    data = [(kanji.literal, i+1, typ, value)
            for i, (typ, value) in enumerate(data)]
    cur.executemany(
        "INSERT INTO %s (literal, seq, type, value) "
        "VALUES (?, ?, ?, ?)" % table_name, data)

def populate_nanori(cur, kanji):
    _populate_val_table(cur, kanji, "nanori", kanji._get_nanori_nodes())

def populate_radical_names(cur, kanji):
    _populate_val_table(cur, kanji, "radical_names",
                        kanji._get_radical_name_nodes())

def populate_radicals(cur, kanji):
    _populate_type_val_table(cur, kanji, "radicals",
                             kanji._get_radical_nodes())

def populate_codepoints(cur, kanji):
    _populate_type_val_table(cur, kanji, "codepoints",
                             kanji._get_codepoint_nodes())

def populate_tables(cur, header, data):
    populate_header(cur, header)
    for kanji in data:
        populate_senses(cur, kanji)
        populate_nanori(cur, kanji)
        populate_misc(cur, kanji)
        populate_codepoints(cur, kanji)
        populate_radicals(cur, kanji)
        populate_radical_names(cur, kanji)
        #populate_variants(cur, kanji)
        #populate_dict_codes(cur, kanji)
        #populate_query_codes(cur, kanji)

def create_db(cur, kd2_fname):
    """Main function for creating a KANJIDIC2-based SQLite database."""
    print "Creating empty tables... "
    create_kanji_tables(cur)
    print "Loading KANJIDIC2 data... "
    header, data = get_data(kd2_fname)
    print "Populating tables... "
    populate_tables(cur, header, data)

def with_db(db_fname, fn, *args, **kwargs):
    conn = sqlite3.connect(db_fname)
    cur = conn.cursor()
    try:
        fn(cur, *args, **kwargs)
    finally:
        cur.close()
        conn.commit()
        conn.close()

def until_yn(prompt):
    while True:
        val = raw_input(prompt).upper()
        if not val:
            continue
        if "YES".startswith(val):
            return True
        if "NO".startswith(val):
            return False

def main():
    kd2_fname = sys.argv[1]
    db_fname = sys.argv[2]
    if os.path.exists(db_fname):
        assert os.path.isfile(db_fname), "Specified path is not a file."
        overwrite = until_yn("File exists; overwrite? [y/n] ")
        if not overwrite:
            exit(1)
        os.remove(db_fname)
    with_db(db_fname, create_db, kd2_fname)
    print "Database created in file %s." % db_fname

if __name__ == "__main__":
    main()
