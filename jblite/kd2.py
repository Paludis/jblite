import os
from helpers import with_db
from jbparse import kanjidic2
import gettext
gettext.install("jblite")


class KD2Converter(object):

    def __init__(self, kd2_fname, db_fname, verbose=False):
        if os.path.exists(db_fname):
            assert os.path.isfile(db_fname), _("Specified path is not a file.")
            assert os.access(db_fname, os.W_OK), \
                _("Cannot write to specified file.")
        self.kd2_fname = kd2_fname
        self.db_fname = db_fname
        self.verbose = verbose

    def run(self):
        parser = kanjidic2.Parser(self.kd2_fname)
        with_db(self.db_fname, self.create_db,
                parser.header, parser.characters)
        if self.verbose:
            print _("Database committed.  Conversion complete.")

    def create_db(self, cur, header, data):
        """Main function for creating a KANJIDIC2-based SQLite database."""
        self.create_tables(cur)
        self.populate_tables(cur, header, data)

    def drop_tables(self, cur):
        if self.verbose:
            print _("Dropping existing tables... ")
        tables = (
            "header",
            "stroke_miscounts",
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

    def create_tables(self, cur):
        """Creates tables for storing kanji information.

        This format should be fully compatible with all data currently
        stored in KANJIDIC2.  (KANJIDIC2 file_version: 4)

        If tables already exist, they will be silently dropped beforehand.

        """
        self.drop_tables(cur)
        if self.verbose:
            print _("Creating empty tables... ")
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

    def populate_tables(self, cur, header, data):
        if self.verbose:
            print _("Populating tables... ")
        self.populate_header(cur, header)
        total_kanji = len(data)
        for i, kanji in enumerate(data):
            if self.verbose:
                if i % 1000 == 0 and i != 0:
                    print _("%d/%d kanji converted.") % (i, total_kanji)
            self.populate_senses(cur, kanji)
            self.populate_nanori(cur, kanji)
            self.populate_misc(cur, kanji)
            self.populate_codepoints(cur, kanji)
            self.populate_radicals(cur, kanji)
            self.populate_radical_names(cur, kanji)
            self.populate_variants(cur, kanji)
            self.populate_dict_codes(cur, kanji)
            self.populate_query_codes(cur, kanji)
        if self.verbose:
            print _("All kanji converted.  Committing...")

    def populate_header(self, cur, header):
        file_version = header.find("file_version").text
        database_version = header.find("database_version").text
        date = header.find("date_of_creation").text
        cur.execute(
            "INSERT INTO header "
            "(file_version, database_version, date_of_creation) VALUES (?, ?, ?)",
            (file_version, database_version, date))

    def populate_meanings(self, cur, kanji, sense, sense_id):
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

    def populate_readings(self, cur, kanji, sense, sense_id):
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

    def populate_senses(self, cur, kanji):
        senses = kanji._get_sense_nodes()
        if not senses:
            return
        for i, sense in enumerate(senses):
            i += 1
            self.populate_readings(cur, kanji, sense, i)
            self.populate_meanings(cur, kanji, sense, i)

    def populate_stroke_miscounts(self, cur, kanji, miscounts):
        data = [(kanji.literal, i+1, count) for i, count in enumerate(miscounts)]
        cur.executemany(
            "INSERT INTO stroke_miscounts (literal, seq, strokes) "
            "VALUES (?, ?, ?)", data)

    def populate_misc(self, cur, kanji):
        strokes, miscounts = kanji.get_strokes()
        grade = kanji.get_grade()
        freq = kanji.get_freq()
        jlpt = kanji.get_jlpt()
        cur.execute(
            "INSERT INTO misc (literal, grade, freq, jlpt, strokes) "
            "VALUES (?, ?, ?, ?, ?)", (kanji.literal, grade, freq, jlpt, strokes))
        if miscounts:
            self.populate_stroke_miscounts(cur, kanji, miscounts)

    def _populate_val_table(self, cur, kanji, table_name, nodes):
        if not nodes:
            return
        data = [(kanji.literal, i+1, node.text) for i, node in enumerate(nodes)]
        cur.executemany(
            "INSERT INTO %s (literal, seq, value) VALUES (?, ?, ?)" % table_name,
            data)

    def _populate_type_val_table(self, cur, kanji, table_name, node_d):
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

    def populate_nanori(self, cur, kanji):
        self._populate_val_table(cur, kanji, "nanori", kanji._get_nanori_nodes())

    def populate_radical_names(self, cur, kanji):
        self._populate_val_table(cur, kanji, "radical_names",
                                 kanji._get_radical_name_nodes())

    def populate_radicals(self, cur, kanji):
        self._populate_type_val_table(cur, kanji, "radicals",
                                      kanji._get_radical_nodes())

    def populate_codepoints(self, cur, kanji):
        self._populate_type_val_table(cur, kanji, "codepoints",
                                      kanji._get_codepoint_nodes())

    def populate_variants(self, cur, kanji):
        self._populate_type_val_table(cur, kanji, "variants",
                                      kanji._get_variant_nodes())

    def populate_dict_codes(self, cur, kanji):
        pass

    def populate_query_codes(self, cur, kanji):
        pass
