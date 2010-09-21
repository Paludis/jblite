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

            self._create_new_tables()
            self._populate_database(etree)
            self.conn.commit()

    def search(self, query, pref_lang=None):
        raise NotImplementedError()

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
            self.cursor.execute("DROP TABLE IF EXISTS %s" % tbl)
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

def parse_args():
    import sys
    from optparse import OptionParser
    op = OptionParser(usage="%prog <db_filename> [search_query]")
    op.add_option("-i", "--initialize",
                  dest="init_fname", metavar="XML_SOURCE",
                  help=_("Initialize database from file."))
    options, args = op.parse_args()
    if len(args) < 1:
        op.print_help()
        exit(-1)
    return (options, args)

def main():
    options, args = parse_args()
    db_fname = args[0]

    if options.init_fname is not None:
        db = Database(db_fname, init_from_file=options.init_fname)
    else:
        db = Database(db_fname)

    # Do search
    if len(args) > 1:
        # To be nice, we'll join all remaining args with spaces.
        search_query = " ".join(args[1:])

        results = db.search(search_query)
        print(results)

if __name__ == "__main__":
    main()
