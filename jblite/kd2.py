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

            entities = self._get_entities(raw_data)
            infile = StringIO(raw_data)
            etree = ElementTree(file=infile)
            infile.close()

            self._create_new_tables()
            self._populate_database(etree, entities)
            self.conn.commit()

    def search(self, query, pref_lang=None):
        raise NotImplementedError()

    def _create_table_objects(self):
        """Creates table objects.

        Returns a dictionary of table name to table object.

        """
        class_mappings = {
            }

        # Set up key/value tables
        kv_tables = [ # key-value tables (id -> text blob)
            ]
        for tbl in kv_tables:
            class_mappings[tbl] = KeyValueTable

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
        pass


class EntryTable(Table):
    create_query = ("CREATE TABLE %s "
                    "(id INTEGER PRIMARY KEY, ent_seq INTEGER)")
    insert_query = "INSERT INTO %s VALUES (NULL, ?)"
    index_queries = [
        "CREATE INDEX %s_seq ON %s (ent_seq)",
        ]


######################################################################

def main():
    if len(sys.argv) < 3:
        print(_("Syntax: %s <db_filename> [xml_source]" % sys.argv[0]),
              file=sys.stderr)
    db = Database(sys.argv[1], init_from_file=sys.argv[2])

if __name__ == "__main__":
    main()
