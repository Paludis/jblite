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

    """Top level object for SQLite 3-based JMdict database."""

    def __init__(self, filename, init_from_file=None):
        self.conn = sqlite3.connect(filename)
        self.cursor = self.conn.cursor()
        self.tables = self._create_tables()
        if init_from_file is not None:
            raw_data = gzread(init_from_file)

            entities = self._get_entities(raw_data)
            infile = StringIO(raw_data)
            etree = ElementTree(file=infile)
            infile.close()

            self._create_new_tables()
            self._populate_database(etree, entities)

    def search(self, query, pref_lang=None):
        raise NotImplementedError()

    def _create_tables(self):
        """Creates table objects.

        Returns a dictionary of table name to table object.

        """
        class_mappings = {
            "entry": EntryTable,     # key->int ID
            "r_ele": REleTable,      # key-value plus nokanji flag
            "sense": SenseTable,     # one-many group mapping for sense info
            "audit": AuditTable,     # key->(update_date, update_details)
            "lsource": LSourceTable, # key -> lang, type=full/part, wasei=t/f
            "gloss": GlossTable,     # key -> lang, g_gend, value, pri flag
            "links": LinksTable,     # key -> tag, desc, uri
            "bibl": BiblTable,       # key -> tag, txt
            #"etym", # not used yet
            "entities": EntityTable,  # Info from JMdict XML entities
            }

        # Set up key/value and key/entity tables
        kv_tables = [ # key-value tables (id -> text blob)
            "k_ele",
            "ke_pri",
            "re_restr",
            "re_pri",
            "stagk",
            "stagr",
            "xref",  # (#PCDATA)* - why the *?
            "ant",   # (#PCDATA)* - why the *?
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
        for tbl in kv_tables:
            class_mappings[tbl] = KeyValueTable
        for tbl in kv_entity_tables:
            class_mappings[tbl] = KeyEntityTable

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

    def _populate_database(self, etree, entities):
        """Imports XML data into SQLite database.

        table_d: table to table_object dictionary
        etree: ElementTree object for JMdict
        entities: entity name to description dictionary

        """
        # Populate entities table and get integer keys
        # NOTE: we'll be mapping from *expanded* entities to ints.
        entity_int = {}
        tbl = self.tables['entities']
        for entity, expansion in entities.iteritems():
            i = tbl.insert(entity, expansion)
            entity_int[expansion] = i

        self.conn.commit()

        # Iterate through each entry
        for i, entry in enumerate(etree.findall("entry")):
            if i >= 10:
                break

            # entry table
            ent_seq = entry.find("ent_seq")
            entry_id = self.tables["entry"].insert(int(ent_seq.text))

            for k_ele in entry.findall("k_ele"):
                # k_ele
                value = k_ele.find("keb").text
                k_ele_id = self.tables["k_ele"].insert(entry_id, value)

                # ke_inf
                for ke_inf in k_ele.findall("ke_inf"):
                    value = ke_inf.text
                    entity_id = entity_int[value]
                    self.tables["ke_inf"].insert(k_ele_id, entity_id)

                # ke_pri
                for ke_pri in k_ele.findall("ke_pri"):
                    value = ke_pri.text
                    self.tables["ke_pri"].insert(k_ele_id, value)

            for r_ele in entry.findall("r_ele"):
                # r_ele
                value = r_ele.find("reb").text
                # For nokanji: currently it's an empty tag, so
                # treating it as true/false.
                nokanji = 1 if r_ele.find("nokanji") is not None else 0
                r_ele_id = self.tables["r_ele"].insert(entry_id, value, nokanji)

                # re_restr
                for re_restr in r_ele.findall("re_restr"):
                    value = re_restr.text
                    self.tables["re_restr"].insert(r_ele_id, value)

                # re_inf
                for re_inf in r_ele.findall("re_inf"):
                    value = re_inf.text
                    entity_id = entity_int[value]
                    self.tables["re_inf"].insert(r_ele_id, entity_id)

                # re_pri
                for re_pri in r_ele.findall("re_pri"):
                    value = re_pri.text
                    self.tables["re_pri"].insert(r_ele_id, value)


            ########################################

            self.conn.commit()

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


class Table(object):

    """Base class for tables."""

    # These queries must be specified in child classes.
    create_query = None
    insert_query = None

    # Index queries are not required.  If specified, they are assumed
    # to take the format:
    #
    #   CREATE INDEX %s_XXX ON %s (YYY)",
    #
    # where %s is a placeholder for the table name, and XXX/YYY are
    # replaced as desired.
    index_queries = []

    def __init__(self, cursor, table_name):
        self.cursor = cursor
        self.__next_id = 1
        self.table_name = table_name

    def create(self):
        """Creates table, plus indices if supplied in class definition."""
        query = self._get_create_query()
        print(query)
        self.cursor.execute(self._get_create_query())
        index_queries = self._get_index_queries()
        for query in index_queries:
            print(query)
            self.cursor.execute(query)
        print()

    def insert(self, *args):
        """Runs an insert with the specified arguments.

        Returns the row id of the insert.  (cursor.lastrowid)

        """
        query = self._get_insert_query()
        print(query, args)
        print()
        self.cursor.execute(query, args)
        print("INSERT result:", self.cursor.lastrowid)
        return self.cursor.lastrowid

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


class SenseTable(Table):
    """Corresponds to <sense> tag.  Functions as group for glosses, etc."""
    create_query = ("CREATE TABLE %s (id INTEGER PRIMARY KEY, fk INTEGER)")
    insert_query = "INSERT INTO %s VALUES (NULL, ?)"
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


######################################################################

def main():
    if len(sys.argv) < 3:
        print(_("Please specify"), file=sys.stderr)
    db = Database(sys.argv[1], init_from_file=sys.argv[2])

if __name__ == "__main__":
    main()
