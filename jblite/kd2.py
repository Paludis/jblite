from __future__ import print_function
from __future__ import with_statement

import os, sys, re, sqlite3, time
from cStringIO import StringIO
from xml.etree.cElementTree import ElementTree
from helpers import gzread
from table import Table, KeyValueTable

import gettext
#t = gettext.translation("jblite")
#_ = t.ugettext
gettext.install("jblite")


# This method of getting the encoding might not be the best...
# but it works for now, and avoids hacks with
# setdefaultencoding.
get_encoding = sys.getfilesystemencoding


class Database(object):

    """Top level object for SQLite 3-based KANJIDIC2 database."""

    def __init__(self, filename, init_from_file=None):
        self.conn = sqlite3.connect(filename)
        self.cursor = self.conn.cursor()
        self.tables = self._create_table_objects()
        if init_from_file is not None:
            raw_data = gzread(init_from_file)

            infile = StringIO(raw_data)
            etree = ElementTree(file=infile)
            infile.close()

            # Create the core database
            self._create_new_tables()
            self._populate_database(etree)
            self.conn.commit()

            # Create supplemental indices
            self._create_index_tables()
            self.conn.commit()

    def search(self, query, lang=None):
        encoding = get_encoding()
        wrapped_query = "%%%s%%" % query  # Wrap in wildcards
        unicode_query = wrapped_query.decode(encoding)

        if os.name == "nt":
            print(u"Searching for \"%s\", lang=%s..." %
                  (unicode_query, repr(lang)),
                  file=sys.stderr)

        # Do some search stuff here...

        # 1. Find by reading

        entries_r = self.search_by_reading(unicode_query)
        entries_m = self.search_by_meaning(unicode_query,
                                           lang=lang)
        entries_n = self.search_by_nanori(unicode_query)

        # DEBUG CODE
        print("READINGS:")
        if len(entries_r) == 0:
            print("No 'reading' results found.")
        for ent_id, literal in entries_r:
            try:
                print(u"ID: %d, literal: %s" % (ent_id, literal))
            except UnicodeEncodeError:
                print(u"ID: %d, literal (repr): %s" % (ent_id, repr(literal)))

        print("NANORI:")
        if len(entries_n) == 0:
            print("No 'nanori' results found.")
        for ent_id, literal in entries_n:
            try:
                print(u"ID: %d, literal: %s" % (ent_id, literal))
            except UnicodeEncodeError:
                print(u"ID: %d, literal (repr): %s" % (ent_id, repr(literal)))

        print("MEANINGS:")
        if len(entries_m) == 0:
            print("No 'meaning' results found.")
        for ent_id, literal in entries_m:
            try:
                print(u"ID: %d, literal: %s" % (ent_id, literal))
            except UnicodeEncodeError:
                print(u"ID: %d, literal (repr): %s" % (ent_id, repr(literal)))

        # Results: character IDs
        results = list(sorted([row[0] for row in
                               (entries_r + entries_m + entries_n)]))

        return results

    def search_by_reading(self, query):
        # reading -> rmgroup -> character
        self.cursor.execute(
            "SELECT id, literal FROM character WHERE id IN "
            "(SELECT fk FROM rmgroup WHERE id IN "
            "(SELECT fk FROM reading WHERE value LIKE ?))", (query,))
        rows = self.cursor.fetchall()
        return rows

    def search_by_nanori(self, query):
        # nanori -> character
        self.cursor.execute(
            "SELECT id, literal FROM character WHERE id IN "
            "(SELECT fk FROM nanori WHERE value LIKE ?)", (query,))
        rows = self.cursor.fetchall()
        return rows

    def search_by_meaning(self, query, lang=None):
        # meaning -> rmgroup -> character
        if lang is None:
            self.cursor.execute(
                "SELECT id, literal FROM character WHERE id IN "
                "(SELECT fk FROM rmgroup WHERE id IN "
                "(SELECT fk FROM meaning WHERE value LIKE ?))", (query,))
        else:
            self.cursor.execute(
                "SELECT id, literal FROM character WHERE id IN "
                "(SELECT fk FROM rmgroup WHERE id IN "
                "(SELECT fk FROM meaning WHERE lang = ? AND value LIKE ?))",
                (lang, query))
        rows = self.cursor.fetchall()
        return rows

    def lookup_by_id(self, character_id):

        def get_single_col(rows):
            return [row[0] for row in rows]

        def skip_id(rows):
            return [row[1:] for row in rows]

        result = {}

        # lookup returns a list of rows, but there'll only be one here...
        literal, grade, freq, jlpt = \
            self.tables['character'].lookup(id=character_id)[0]
        result['literal'] = literal
        result['grade'] = grade
        result['freq'] = freq
        result['jlpt'] = jlpt

        result['codepoints'] = \
            skip_id(self.tables['codepoint'].lookup(fk=character_id))
        result['radicals'] = \
            skip_id(self.tables['radical'].lookup(fk=character_id))

        # Strokes: ignore ID column, take only stroke count.
        result['strokes'] = \
            get_single_col(skip_id(
                self.tables['stroke_count'].lookup(fk=character_id)))

        result['variants'] = \
            skip_id(self.tables['variant'].lookup(fk=character_id))
        result['rad_names'] = \
            skip_id(self.tables['rad_name'].lookup(fk=character_id))
        result['dic_numbers'] = \
            skip_id(self.table['dic_number'].lookup(fk=character_id))
        result['query_codes'] = \
            skip_id(self.table['query_code'].lookup(fk=character_id))

        # Readings/meanings
        rmgroup_ids = get_single_col(
            self.tables['rmgroup'].lookup(fk=character_id))
        rmgroups = []
        for rmgroup_id in rmgroup_ids:
            rmgroup = {}
            rmgroup['readings'] = \
                skip_id(self.tables['reading'].lookup(fk=rmgroup_id))
            rmgroup['meanings'] = \
                skip_id(self.tables['meaning'].lookup(fk=rmgroup_id))
            rmgroups.append(rmgroup)
        result['rmgroups'] = rmgroups

        result['nanori'] = \
            skip_id(self.tables['nanori'].lookup(fk=character_id))

        return result

    def lookup_by_literal(self, literal):
        self.cursor.execute("SELECT id FROM character WHERE literal = ?",
                            (literal,))
        rows = self.cursor.fetchall()
        if len(rows) < 1:
            return None
        else:
            return rows[0][0]

    def _create_table_objects(self):
        """Creates table objects.

        Returns a dictionary of table name to table object.

        """
        class_mappings = {
            "header": HeaderTable,
            "character": CharacterTable,
            "codepoint": TypeValueTable,
            "radical": TypeValueTable,
            "stroke_count": StrokeCountTable,
            "variant": TypeValueTable,
            "rad_name": KeyValueTable,
            "dic_number": DicNumberTable,
            "query_code": QueryCodeTable,
            "rmgroup": RMGroupTable,
            "reading": ReadingTable,
            "meaning": MeaningTable,
            "nanori": KeyValueTable,
            }

        # Create all table objects
        table_mappings = {}
        for tbl, cls in class_mappings.iteritems():
            table_mappings[tbl] = cls(self.cursor, tbl)

        return table_mappings

    def _create_new_tables(self):
        """(Re)creates the database tables."""
        for tbl, tbl_obj in self.tables.iteritems():
            self._drop_table(tbl)
            tbl_obj.create()

    def _populate_database(self, etree):
        """Imports XML data into SQLite database.

        table_d: table to table_object dictionary
        etree: ElementTree object for KANJIDIC2

        """
        # Grab header
        header = etree.find("header")
        file_ver = header.find("file_version").text
        db_ver = header.find("database_version").text
        date = header.find("date_of_creation").text
        self.tables['header'].insert(file_ver, db_ver, date)

        # Iterate through characters
        for character in etree.findall("character"):
            # Character table
            literal = character.find("literal").text

            # Grab misc node - we'll store a few things from it in the
            # main character table, too.
            misc = character.find("misc")
            grade = misc.find("grade")
            grade = int(grade.text) if grade is not None else None
            freq = misc.find("freq")
            freq = int(freq.text) if freq is not None else None
            jlpt = misc.find("jlpt")
            jlpt = int(jlpt.text) if jlpt is not None else None

            char_id = self.tables['character'].insert(literal, grade,
                                                      freq, jlpt)

            table = self.tables['codepoint']
            codepoint = character.find("codepoint")
            for cp_value in codepoint.findall("cp_value"):
                value = cp_value.text
                cp_type = cp_value.get("cp_type")
                table.insert(char_id, cp_type, value)

            table = self.tables['radical']
            radical = character.find("radical")
            for rad_value in radical.findall("rad_value"):
                value = rad_value.text
                rad_type = rad_value.get("rad_type")
                table.insert(char_id, rad_type, value)

            # Tables generated from <misc> begin here
            table = self.tables['stroke_count']
            for stroke_count in misc.findall("stroke_count"):
                count = int(stroke_count.text)
                table.insert(char_id, count)

            table = self.tables['variant']
            for variant in misc.findall("variant"):
                value = variant.text
                var_type = variant.get("var_type")
                table.insert(char_id, var_type, value)

            table = self.tables['rad_name']
            for rad_name in misc.findall("rad_name"):
                value = rad_name.text
                table.insert(char_id, value)

            # Remaining direct descendents of <character>...
            dic_number = character.find("dic_number")
            if dic_number is not None:
                table = self.tables['dic_number']
                for dic_ref in dic_number.findall("dic_ref"):
                    dr_type = dic_ref.get("dr_type")
                    m_vol = dic_ref.get("m_vol", None)
                    m_page = dic_ref.get("m_page", None)
                    value = dic_ref.text
                    table.insert(char_id, dr_type, m_vol, m_page, value)

            query_code = character.find("query_code")
            if query_code is not None:
                table = self.tables['query_code']
                for q_code in query_code.findall("q_code"):
                    qc_type = q_code.get("qc_type")
                    skip_misclass = q_code.get("skip_misclass", None)
                    value = q_code.text
                    table.insert(char_id, qc_type, skip_misclass, value)

            reading_meaning = character.find("reading_meaning")
            if reading_meaning is not None:
                table = self.tables['rmgroup']
                for rmgroup in reading_meaning.findall("rmgroup"):
                    group_id = table.insert(char_id)
                    table = self.tables['reading']
                    for reading in rmgroup.findall("reading"):
                        r_type = reading.get("r_type")
                        on_type = reading.get("on_type")
                        r_status = reading.get("r_status")
                        value = reading.text
                        table.insert(group_id, r_type, on_type, r_status, value)
                    table = self.tables['meaning']
                    for meaning in rmgroup.findall("meaning"):
                        lang = meaning.get("m_lang", "en")
                        value = meaning.text
                        table.insert(group_id, lang, value)
                table = self.tables['nanori']
                for nanori in reading_meaning.findall("nanori"):
                    table.insert(char_id, nanori.text)

    def _drop_table(self, name):
        self.cursor.execute("DROP TABLE IF EXISTS %s" % name)

    def _create_index_tables(self):
        """Creates extra tables to help with common searches.

        Supplementary tables include:

        1. Reading search table: kun-yomi to character ID.  Kun-yomi
           is modified for easier searching (no "." or "-" markers).

        """
        self._create_reading_search_table()

    def _create_reading_search_table(self):
        """Creates "sanitized" reading to character ID search table."""

        # Get all kunyomi strings and their foreign keys
        self.cursor.execute('SELECT fk, value FROM reading '
                            'WHERE type="ja_kun"')
        rows = self.cursor.fetchall()
        reading_fks, values = zip(*rows)  # unzip idiom (see zip doc)

        # Sanitize strings by removing "." and "-"
        values = [value.replace(u".", u"").replace(u"-", u"")
                  for value in values]

        # Resolve foreign keys to reading group foreign keys
        # (character IDs)
        d = {}  # kunyomi fk to reading group fk mapping

        # Get all reading group IDs and their foreign keys (character IDs)
        # (reading group ID is a reading FK (which we have),
        #  and reading group FK is the character ID (which we want).)
        self.cursor.execute("SELECT id, fk FROM rmgroup")
        for _id, fk in self.cursor.fetchall():
            d[_id] = fk

        # Convert reading group foreign keys from the readings into
        # character IDs.
        entry_ids = [d[reading_fk] for reading_fk in reading_fks]

        # Create new table
        tbl_name = "kunyomi_lookup"
        self.tables[tbl_name] = tbl = ReadingLookupTable(self.cursor, tbl_name)
        self._drop_table(tbl_name)
        tbl.create()

        # Store all sanitized strings and their keys in the table
        rows = zip(values, entry_ids)
        tbl.insertmany(rows)


######################################################################
# KANJIDIC2 data tables
######################################################################


class HeaderTable(Table):
    create_query = ("CREATE TABLE %s "
                    "(file_version TEXT, "
                    "database_version TEXT, "
                    "date_of_creation TEXT)")
    insert_query = "INSERT INTO %s VALUES (?, ?, ?)"


class CharacterTable(Table):
    create_query = ("CREATE TABLE %s "
                    "(id INTEGER PRIMARY KEY, literal TEXT, "
                    "grade INTEGER, freq INTEGER, jlpt INTEGER)")
    insert_query = "INSERT INTO %s VALUES (NULL, ?, ?, ?, ?)"
    index_queries = [
        "CREATE INDEX %s_literal ON %s (literal)",
        ]


class TypeValueTable(Table):
    create_query = ("CREATE TABLE %s "
                    "(id INTEGER PRIMARY KEY, fk INTEGER, "
                    "type TEXT, value TEXT)")
    insert_query = "INSERT INTO %s VALUES (NULL, ?, ?, ?)"
    index_queries = [
        "CREATE INDEX %s_fk ON %s (fk)",
        ]


class StrokeCountTable(Table):
    create_query = ("CREATE TABLE %s (id INTEGER PRIMARY KEY, "
                    "fk INTEGER, count INTEGER)")
    insert_query = "INSERT INTO %s VALUES (NULL, ?, ?)"
    index_queries = [
        "CREATE INDEX %s_fk ON %s (fk)",
        ]


class DicNumberTable(Table):
    create_query = ("CREATE TABLE %s "
                    "(id INTEGER PRIMARY KEY, fk INTEGER, "
                    "type TEXT, m_vol TEXT, m_page TEXT, value TEXT)")
    insert_query = "INSERT INTO %s VALUES (NULL, ?, ?, ?, ?, ?)"
    index_queries = [
        "CREATE INDEX %s_fk ON %s (fk)",
        ]


class QueryCodeTable(Table):
    create_query = ("CREATE TABLE %s "
                    "(id INTEGER PRIMARY KEY, fk INTEGER, "
                    "type TEXT, skip_misclass TEXT, value TEXT)")
    insert_query = "INSERT INTO %s VALUES (NULL, ?, ?, ?, ?)"
    index_queries = [
        "CREATE INDEX %s_fk ON %s (fk)",
        ]


class RMGroupTable(Table):
    create_query = ("CREATE TABLE %s (id INTEGER PRIMARY KEY, fk INTEGER)")
    insert_query = "INSERT INTO %s VALUES (NULL, ?)"
    index_queries = [
        "CREATE INDEX %s_fk ON %s (fk)",
        ]

class ReadingTable(Table):
    create_query = ("CREATE TABLE %s "
                    "(id INTEGER PRIMARY KEY, fk INTEGER, "
                    "type TEXT, on_type TEXT, r_status TEXT, value TEXT)")
    insert_query = "INSERT INTO %s VALUES (NULL, ?, ?, ?, ?, ?)"
    index_queries = [
        "CREATE INDEX %s_fk ON %s (fk)",
        "CREATE INDEX %s_value ON %s (value)",
        ]


class MeaningTable(Table):
    create_query = ("CREATE TABLE %s "
                    "(id INTEGER PRIMARY KEY, fk INTEGER, "
                    "lang TEXT, value TEXT)")
    insert_query = "INSERT INTO %s VALUES (NULL, ?, ?, ?)"
    index_queries = [
        "CREATE INDEX %s_fk ON %s (fk)",
        "CREATE INDEX %s_lang_value ON %s (lang, value)",
        ]


######################################################################
# Index tables (not part of actual KANJIDIC2)
######################################################################


class ReadingLookupTable(Table):
    """Maps reading to character IDs."""
    # Used for: kunyomi (KANJIDIC2 r_type==ja_kun)
    create_query = ("CREATE TABLE %s "
                    "(id INTEGER PRIMARY KEY, "
                    "reading TEXT, character_id INTEGER)")
    insert_query = "INSERT INTO %s VALUES (NULL, ?, ?)"
    index_queries = [
        "CREATE INDEX %s_reading ON %s (reading)",
        ]



######################################################################

def parse_args():
    from optparse import OptionParser
    op = OptionParser(usage="%prog [options] <db_filename> [search_query]")
    op.add_option("-i", "--initialize",
                  dest="init_fname", metavar="XML_SOURCE",
                  help=_("Initialize database from file."))
    op.add_option("-s", "--search", action="store_true",
                  help=_("Search for kanji by readings or meanings"))
    op.add_option("-l", "--lookup", action="store_true",
                  help=_("Look up exact character"))
    op.add_option("-L", "--lang",
                  help=_("Specify preferred language for searching."))
    options, args = op.parse_args()
    if len(args) < 1:
        op.print_help()
        exit(-1)
    if options.lookup and options.search:
        print(_("Cannot --lookup and --search at the same time."),
              file=sys.stderr)
        exit(-1)
    return (options, args)

def main():
    options, args = parse_args()
    db_fname = args[0]

    if options.init_fname is not None:
        db = Database(db_fname, init_from_file=options.init_fname)
    else:
        db = Database(db_fname)

    if options.search and len(args) > 1:
        # Do search
        # To be nice, we'll join all remaining args with spaces.
        search_query = " ".join(args[1:])

        if options.lang is not None:
            results = db.search(search_query, lang=options.lang)
        else:
            results = db.search(search_query)
        print("Result: %s" % repr(results))
    elif options.lookup and len(args) > 1:
        # Do lookup
        print("Doing lookup...")
        encoding = get_encoding()
        lookup_query = args[1].decode(encoding)
        results = []
        for character in lookup_query:
            result = db.lookup_by_literal(character)
            if result is not None:
                results.append(result)
        print("Result: %s" % repr(results))

    # To do: visualize results
    # Not as important; now we know we can at least do our needed
    # lookups...

if __name__ == "__main__":
    main()
