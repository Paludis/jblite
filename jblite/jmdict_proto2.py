from __future__ import print_function
from __future__ import with_statement

import os, sys, re, sqlite3
from cStringIO import StringIO
from xml.etree.cElementTree import ElementTree
from helpers import gzread

import gettext
#t = gettext.translation("jblite")
#_ = t.ugettext
gettext.install("jblite")



class Database(object):

    def __init__(self, filename, init_from_file=None):
        self.conn = sqlite3.connect(filename)
        self.cursor = self.conn.cursor()
        if init_from_file is not None:
            self._reset_database()
            self._init_from_file(init_from_file)

    def search(self, query, pref_lang=None):
        raise NotImplementedError()

    def _reset_database(self):
        other_tables = {
            "entry": EntryTable,     # key->int ID
            "r_ele": REleTable,      # key-value plus nokanji flag
            "audit": AuditTable,     # key->(update_date, update_details)
            "lsource": LSourceTable, # key -> lang, type=full/part, wasei=t/f
            "gloss": GlossTable,     # key -> lang, g_gend, value, pri flag
            "links": LinksTable,     # key -> tag, desc, uri
            "bibl": BiblTable,       # key -> tag, txt
            #"etym", # not used yet
            "entities": EntityTable,  # Info from JMdict XML entities
            }
        kv_tables = [ # key-value tables (id -> text blob)
            "k_ele",
            "ke_pri",
            "re_restr",
            "re_pri",
            "stagk",
            "stagr",
            "xref",
            "ant",
            "s_inf",
            "example",
            "pri",
            ]
        kv_entity_tables = [ # key-value tables where val == entity
            "ke_inf",
            "re_inf",
            "dial",
            "field",
            "misc",
            "pos",
            ]

        # Drop any existing tables
        all_tables = other_tables.keys() + kv_tables + kv_entity_tables
        for tbl in all_tables:
            self.cursor.execute("DROP TABLE IF EXISTS %s" % tbl)

        # Create mappings of table name to class
        class_mappings = other_tables
        for tbl in kv_tables:
            class_mappings[tbl] = KeyValueTable
        for tbl in kv_entity_tables:
            class_mappings[tbl] = KeyEntityTable

        # Create all table objects
        table_mappings = {}
        for tbl, cls in class_mappings.iteritems():
            table_mappings[tbl] = cls(self.cursor, tbl)

        # Create all tables in DB
        for tbl_obj in table_mappings.itervalues():
            tbl_obj.create()

    def _init_from_file(self, jmdict_src):
        raw_data = gzread(jmdict_src)
        entities = self._get_entities(raw_data)

        infile = StringIO(raw_data)
        etree = ElementTree(file=infile)
        infile.close()

        self._process_etree(etree, entities)

    def _get_entities(self, xml_data):
        """Gets the ENTITY definitions from JMdict.

        Finds the built-in DTD and extracts all ENTITY definitions.

        """
        dtd = self._get_dtd(xml_data)
        # do some logic to find all entities...
        entities = {}
        regex = "<!ENTITY[ ]+([a-zA-Z-]+)[ ]+['\"](.*?)['\"]>"
        for match in re.finditer(regex, xml_data):
            key, value = match.groups()[0:2]
            key = "&%s;" % key  # Convert to &entity; format
            entities[key] = value
        return entities

    def _get_dtd(self, xml_data):
        """Gets the DTD from JMdict."""
        # This works for JMdict (as it is at the time of writing), but is
        # not a general solution.
        start_index = xml_data.find("<!DOCTYPE")
        if start_index == -1:
            raise Exception("Could not find start of internal DTD")
        end_index = xml_data.find("]>")
        if end_index == -1:
            raise Exception("Could not find end ofinternal DTD")
        end_index += 2
        dtd = xml_data[start_index:end_index]
        return dtd

    def _process_etree(self, etree, entities):
        for i, elem in enumerate(etree.getiterator("entry")):
            if i >= 10:
                break
            print(i, elem)


class Table(object):

    """Base class for tables."""

    # These queries must be specified in child classes.
    create_query = None
    insert_query = None
    index_queries = []

    def __init__(self, cursor, table_name):
        self.cursor = cursor
        self.__next_id = 1
        self.table_name = table_name

    def create(self):
        """Creates table, plus indices if supplied in class definition."""
        self.cursor.execute(self._get_create_query())
        index_queries = self._get_index_queries()
        for query in index_queries:
            self.cursor.execute(query)

    def insert(self, *args):
        self.cursor.execute(self._get_insert_query(), args)

    def _get_create_query(self):
        if self.table_name is None:
            raise ValueError(
                "table_name must be specified in class definition")
        return self.create_query % self.table_name

    def _get_insert_query(self):
        if self.table_name is None:
            raise ValueError(
                "table_name must be specified in class definition")
        return self.insert_query % self.table_name

    def _get_index_queries(self):
        if self.table_name is None:
            raise ValueError(
                "table_name must be specified in class definition")
        if (not (isinstance(self.index_queries, list))
          or (len(self.index_queries) == 0)):
            return []
        else:
            # Each query needs to have the table name merged in two
            # places.
            queries = [q % (self.table_name, self.table_name)
                       for q in self.index_queries]
            return queries


class EntryTable(Table):
    create_query = ("CREATE TABLE %s "
                    "(id INTEGER PRIMARY KEY, ent_seq INTEGER)")
    insert_query = "INSERT INTO %s VALUES (NULL, ?)"
    index_queries = [
        "CREATE INDEX %s_seq ON %s (ent_seq)",
        ]


class KeyValueTable(Table):
    """General key/value table for one-many relations."""
    create_query = ("CREATE TABLE %s "
                    "(id INTEGER PRIMARY KEY, fk INTEGER, value TEXT)")
    insert_query = "INSERT INTO %s VALUES (NULL, ?, ?)"
    index_queries = [
        "CREATE INDEX %s_fk ON %s (fk)",
        ]


class KeyEntityTable(KeyValueTable):
    """Just like a KeyValueTable, but with 'entity' instead of 'value'."""
    create_query = ("CREATE TABLE %s "
                    "(id INTEGER PRIMARY KEY, fk INTEGER, entity INTEGER)")


class REleTable(Table):
    create_query = ("CREATE TABLE %s "
                    "(id INTEGER PRIMARY KEY, fk INTEGER,"
                    " value TEXT, nokanji INTEGER)")
    insert_query = "INSERT INTO %s VALUES (NULL, ?, ?, ?)"
    index_queries = [
        "CREATE INDEX %s_fk ON %s (fk)",
        ]


class AuditTable(Table):
    create_query = ("CREATE TABLE %s "
                    "(id INTEGER PRIMARY KEY, fk INTEGER,"
                    " update_date TEXT, update_details TEXT)")
    insert_query = "INSERT INTO %s VALUES (NULL, ?, ?, ?)"
    index_queries = [
        "CREATE INDEX %s_fk ON %s (fk)",
        ]


class LSourceTable(Table):
    """Represents the <lsource> element from JMdict.

    Important changes:
    ls_type=full/part => partial=1/0

    """
    create_query = ("CREATE TABLE %s "
                    "(id INTEGER PRIMARY KEY, fk INTEGER,"
                    " lang TEXT, partial INTEGER, wasei INTEGER)")
    insert_query = "INSERT INTO %s VALUES (NULL, ?, ?, ?, ?)"
    index_queries = [
        "CREATE INDEX %s_fk ON %s (fk)",
        ]


class GlossTable(Table):
    create_query = ("CREATE TABLE %s "
                    "(id INTEGER PRIMARY KEY, fk INTEGER,"
                    " lang TEXT, g_gend TEXT, value TEXT, pri INTEGER)")
    insert_query = "INSERT INTO %s VALUES (NULL, ?, ?, ?, ?, ?)"
    index_queries = [
        "CREATE INDEX %s_fk ON %s (fk)",
        "CREATE INDEX %s_lang ON %s (lang)",
        "CREATE INDEX %s_value ON %s (value)",
        ]


class LinksTable(Table):
    create_query = ("CREATE TABLE %s "
                    "(id INTEGER PRIMARY KEY, fk INTEGER,"
                    " tag TEXT, desc TEXT, uri TEXT)")
    insert_query = "INSERT INTO %s VALUES (NULL, ?, ?, ?, ?)"
    index_queries = [
        "CREATE INDEX %s_fk ON %s (fk)",
        ]


class BiblTable(Table):
    create_query = ("CREATE TABLE %s "
                    "(id INTEGER PRIMARY KEY, fk INTEGER,"
                    " tag TEXT, txt TEXT)")
    insert_query = "INSERT INTO %s VALUES (NULL, ?, ?, ?, ?)"
    index_queries = [
        "CREATE INDEX %s_fk ON %s (fk)",
        ]


class EntityTable(Table):
    table_name = "entities"
    create_query = ("CREATE TABLE %s "
                    "(id INTEGER PRIMARY KEY, entity TEXT, expansion TEXT)")
    insert_query = "INSERT INTO %s VALUES (NULL, ?, ?)"
    index_queries = [
        "CREATE INDEX %s_entity ON %s (entity)",
        ]


def main():
    if len(sys.argv) < 3:
        print(_("Please specify"), file=sys.stderr)
    db = Database(sys.argv[1], init_from_file=sys.argv[2])

if __name__ == "__main__":
    main()
