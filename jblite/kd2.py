# -*- coding: utf-8 -*-
from __future__ import print_function
from __future__ import with_statement

import os, sys, re, sqlite3, time
from cStringIO import StringIO
from xml.etree.cElementTree import ElementTree
from helpers import gzread
from db import Database as BaseDatabase
from table import Table, ChildTable, KeyValueTable

import gettext
#t = gettext.translation("jblite")
#_ = t.ugettext
gettext.install("jblite")


# This method of getting the encoding might not be the best...
# but it works for now, and avoids hacks with
# setdefaultencoding.
get_encoding = sys.getfilesystemencoding


def convert_kunyomi(coded_str):
    """Converts a kunyomi string with ./- to a user-friendly format.

    Specifically, two things occur:

    1. Strings are split on '.' and the right half, if any, is
       enclosed in parentheses.

    2. '-' is replaced with '～'.

    """
    pieces = coded_str.split(u'.', 1)
    if len(pieces) > 1:
        intermediate = u"".join([pieces[0], u"(", pieces[1], u")"])
    else:
        intermediate = pieces[0]
    result = intermediate.replace(u"-", u"～")
    return result

def get_jouyou_str(grade_int):
    """Converts an integer Jouyou grade code into a string."""
    # DO LATER
    return str(grade_int)


class Entry(object):

    def __init__(self, record):
        self._record = record

    def __unicode__(self):
        """Basic string representation of the entry."""

        char_rec = self._record
        lines = []

        literal = char_rec.data["literal"]
        lines.append(_(u"Literal: %s (0x%X)") % (literal, ord(literal)))

        rmgroup_recs = char_rec.find_children("rmgroup")
        for i, rmgroup_rec in enumerate(rmgroup_recs):
            group_index = i + 1
            lines.append(_(u"Group %d:") % group_index)

            reading_recs = rmgroup_rec.find_children("reading")

            kunyomi = [r.data['value'] for r in reading_recs
                       if r.data["type"] == "ja_kun"]
            # kun-yomi needs ./- translated
            kunyomi = map(convert_kunyomi, kunyomi)
            lines.append(_(u"  Kun-yomi: %s") % u"、".join(kunyomi))

            onyomi = [r.data['value'] for r in reading_recs
                      if r.data["type"] == "ja_on"]
            lines.append(_(u"  On-yomi: %s") % u"、".join(onyomi))

            meaning_recs = rmgroup_rec.find_children("meaning")
            meaning_d = {}
            for r in meaning_recs:
                meanings = meaning_d.setdefault(r.data['lang'], [])
                meanings.append(r.data['value'])
            for lang in sorted(meaning_d.keys()):
                meanings = meaning_d[lang]
                meaning_str = "; ".join(meanings)
                lines.append(_(u"  Meanings (%s): %s") % (lang, meaning_str))

        nanori_recs = char_rec.find_children("nanori")
        if len(nanori_recs) > 0:
            nanori = [r.data["value"] for r in nanori_recs]
            nanori_str = u"、".join(nanori)
            lines.append(_(u"Nanori: %s") % nanori_str)

        stroke_recs = char_rec.find_children("stroke_count")
        strokes = [r.data['count'] for r in stroke_recs]
        if len(strokes) == 1:
            lines.append(_(u"Stroke count: %d") % strokes[0])
        elif len(strokes) > 1:
            miscounts = ", ".join(map(str, strokes[1:]))
            lines.append(_(u"Stroke count: %d (miscounts: %s)") %
                         (strokes[0], miscounts))
        else:
            pass # No stroke count info; don't print anything

        freq = char_rec.data["freq"]
        if freq is not None:
            lines.append(_(u"Frequency: %d") % freq)

        grade = char_rec.data["grade"]
        if grade is not None:
            # Jouyou grade codes has special meanings; a conversion is
            # needed.
            grade_str = get_jouyou_str(grade)
            lines.append(_(u"Jouyou grade: %s") % grade_str)

        jlpt = char_rec.data["jlpt"]
        if jlpt is not None:
            lines.append(_(u"JLPT grade: %d") % jlpt)

        return u"\n".join(lines)

    def __repr__(self):
        return repr(self._record)


class Database(BaseDatabase):

    """Top level object for SQLite 3-based KANJIDIC2 database."""

    entry_class = Entry
    table_map = {
        u"character": {
            u"codepoint": {},
            u"radical": {},
            u"stroke_count": {},
            u"variant": {},
            u"rad_name": {},
            u"dic_number": {},
            u"query_code": {},
            u"rmgroup": {
                u"reading": {},
                u"meaning": {},
                },
            u"nanori": {},
            }
        }

    def __init__(self, filename, init_from_file=None):
        self.conn = sqlite3.connect(filename)
        self.conn.row_factory = sqlite3.Row  # keyword accessors for rows
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

    def search(self, query, lang=None, options=None):
        encoding = get_encoding()
        wrapped_query = "%%%s%%" % query  # Wrap in wildcards
        unicode_query = wrapped_query.decode(encoding)

        verbose = (options is not None) and (options.verbose == True)

        if verbose and os.name == "nt":
            print(u"Searching for \"%s\", lang=%s..." %
                  (unicode_query, repr(lang)),
                  file=sys.stderr)

        # Do some search stuff here...

        # 1. Find by reading

        entries_r = self._search_by_reading(unicode_query)
        entries_m = self._search_by_meaning(unicode_query,
                                            lang=lang)
        entries_n = self._search_by_nanori(unicode_query)
        entries_i = self._search_by_indices(unicode_query, lang=lang)

        # DEBUG CODE
        if verbose:
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

            print("INDICES:")
            if len(entries_i) == 0:
                print("No indexed results found.")
            for ent_id in entries_i:
                print(u"ID: %d" % (ent_id,))

        # Get list of unique character IDs
        char_ids = []
        for lst in (entries_r, entries_m, entries_n):
            for row in lst:
                if row[0] not in char_ids:
                    char_ids.append(row[0])
        for char_id in entries_i:
            if char_id not in char_ids:
                char_ids.append(char_id)

        char_ids = list(sorted(char_ids))

        results = [self.lookup(char_id) for char_id in char_ids]
        return results

    def _search_by_reading(self, query):
        # reading -> rmgroup -> character
        self.cursor.execute(
            "SELECT id, literal FROM character WHERE id IN "
            "(SELECT fk FROM rmgroup WHERE id IN "
            "(SELECT fk FROM reading WHERE value LIKE ?))", (query,))
        rows = self.cursor.fetchall()
        return rows

    def _search_by_nanori(self, query):
        # nanori -> character
        self.cursor.execute(
            "SELECT id, literal FROM character WHERE id IN "
            "(SELECT fk FROM nanori WHERE value LIKE ?)", (query,))
        rows = self.cursor.fetchall()
        return rows

    def _search_by_meaning(self, query, lang=None):
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

    def _search_by_indices(self, query, lang=None):
        # Get IDs from index table
        # Note: lang is currently unused.
        self.cursor.execute(
            "SELECT character_id FROM kunyomi_lookup WHERE reading LIKE ?",
            (query,))
        rows = self.cursor.fetchall()
        return [row[0] for row in rows]

    def search_by_literal(self, literal):
        # Not much of a "search", but avoids overlap with BaseDictionary.lookup.
        self.cursor.execute("SELECT id FROM character WHERE literal = ?",
                            (literal,))
        rows = self.cursor.fetchall()
        if len(rows) < 1:
            return None
        else:
            char_id = rows[0][0]
            return self.lookup(char_id)

    def lookup(self, id):
        return BaseDatabase.lookup(self, "character", id)

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

        # Mapping is from reading to character ID...
        # r.fk -> rg.id, rg.fk -> c.id.
        query = (
            "SELECT r.value, c.id "
            "FROM reading r, rmgroup rg, character c "
            'WHERE r.type = "ja_kun" AND r.fk = rg.id AND rg.fk = c.id'
            )
        self.cursor.execute(query)
        rows = self.cursor.fetchall()
        values, ids = zip(*rows)  # unzip idiom (see zip doc)

        # Sanitize strings by removing "." and "-"
        values = [value.replace(u".", u"").replace(u"-", u"")
                  for value in values]

        # Create new table
        tbl_name = "kunyomi_lookup"
        self.tables[tbl_name] = tbl = ReadingLookupTable(self.cursor, tbl_name)
        self._drop_table(tbl_name)
        tbl.create()

        # Store all sanitized strings and their keys in the table
        rows = zip(values, ids)
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


class TypeValueTable(ChildTable):
    create_query = ("CREATE TABLE %s "
                    "(id INTEGER PRIMARY KEY, fk INTEGER, "
                    "type TEXT, value TEXT)")
    insert_query = "INSERT INTO %s VALUES (NULL, ?, ?, ?)"
    index_queries = [
        "CREATE INDEX %s_fk ON %s (fk)",
        ]


class StrokeCountTable(ChildTable):
    create_query = ("CREATE TABLE %s (id INTEGER PRIMARY KEY, "
                    "fk INTEGER, count INTEGER)")
    insert_query = "INSERT INTO %s VALUES (NULL, ?, ?)"
    index_queries = [
        "CREATE INDEX %s_fk ON %s (fk)",
        ]


class DicNumberTable(ChildTable):
    create_query = ("CREATE TABLE %s "
                    "(id INTEGER PRIMARY KEY, fk INTEGER, "
                    "type TEXT, m_vol TEXT, m_page TEXT, value TEXT)")
    insert_query = "INSERT INTO %s VALUES (NULL, ?, ?, ?, ?, ?)"
    index_queries = [
        "CREATE INDEX %s_fk ON %s (fk)",
        ]


class QueryCodeTable(ChildTable):
    create_query = ("CREATE TABLE %s "
                    "(id INTEGER PRIMARY KEY, fk INTEGER, "
                    "type TEXT, skip_misclass TEXT, value TEXT)")
    insert_query = "INSERT INTO %s VALUES (NULL, ?, ?, ?, ?)"
    index_queries = [
        "CREATE INDEX %s_fk ON %s (fk)",
        ]


class RMGroupTable(ChildTable):
    create_query = ("CREATE TABLE %s (id INTEGER PRIMARY KEY, fk INTEGER)")
    insert_query = "INSERT INTO %s VALUES (NULL, ?)"
    index_queries = [
        "CREATE INDEX %s_fk ON %s (fk)",
        ]

class ReadingTable(ChildTable):
    create_query = ("CREATE TABLE %s "
                    "(id INTEGER PRIMARY KEY, fk INTEGER, "
                    "type TEXT, on_type TEXT, r_status TEXT, value TEXT)")
    insert_query = "INSERT INTO %s VALUES (NULL, ?, ?, ?, ?, ?)"
    index_queries = [
        "CREATE INDEX %s_fk ON %s (fk)",
        "CREATE INDEX %s_value ON %s (value)",
        ]


class MeaningTable(ChildTable):
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
    op.add_option("-v", "--verbose", action="store_true",
                  help=_("Verbose mode (print debug strings)"))
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

    results = []
    if len(args) <= 1:
        # No search was requested; we can exit here.
        return

    if options.search == True:
        # Do search
        # To be nice, we'll join all remaining args with spaces.
        search_query = " ".join(args[1:])

        if options.lang is not None:
            results = db.search(search_query,
                                lang=options.lang, options=options)
        else:
            results = db.search(search_query, options=options)
    elif options.lookup == True:
        # Do lookup
        encoding = get_encoding()
        lookup_query = args[1].decode(encoding)
        results = []
        for character in lookup_query:
            result = db.search_by_literal(character)
            if result is not None:
                results.append(result)
    else:
        # No lookup
        print(_("For searches or lookups, the --search or --lookup flag is "
                "required."))
        return

    # To do: visualize results
    # Not as important; now we know we can at least do our needed
    # lookups...
    if len(results) > 0:
        encoding = get_encoding()
        # DEBUG: until lookup_by_id is implemented, this will work.
        for index, result in enumerate(results):
            index += 1
            print(_("[Entry %d]") % index)

            print(unicode(result).encode(encoding))
            print()
    else:
        print(_("No results found."))

if __name__ == "__main__":
    main()
