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
            "entity": EntityTable,  # Info from JMdict XML entities
            }

        # Set up key/value and key/entity tables
        kv_tables = [ # key-value tables (id -> text blob)
            "k_ele",
            "ke_pri",
            "re_restr",
            "re_pri",
            "etym",
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
        # NOTE: this is waaay too long.  Should be broken up somehow.
        # For now this will work though...

        # Populate entities table and get integer keys
        # NOTE: we'll be mapping from *expanded* entities to ints.
        entity_int = {}
        tbl = self.tables['entity']
        for entity, expansion in entities.iteritems():
            i = tbl.insert(entity, expansion)
            entity_int[expansion] = i

        self.conn.commit()

        # Iterate through each entry
        print("========================================")
        for i, entry in enumerate(etree.findall("entry")):
            if i >= 200:
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

            # info
            # (Although children of an info node, since there's only
            # one per entry, let's connect directly to the entry.)
            info = entry.find("info")
            if info is not None:
                for links in info.findall("links"):
                    link_tag = links.find("link_tag")
                    link_desc = links.find("link_desc")
                    link_uri = links.find("link_uri")
                    self.tables["links"].insert(entry_id, link_tag, link_desc,
                                                link_uri)
                for bibl in info.findall("bibl"):
                    bib_tag = links.find("bib_tag")
                    bib_txt = links.find("bib_txt")
                    bib_tag = bib_tag.text if bib_tag is not None else ""
                    bib_txt = bib_txt.text if bib_txt is not None else ""
                    self.tables["bibl"].insert(entry_id, bib_tag, bib_txt)
                for etym in info.findall("etym"):
                    self.tables["etym"].insert(entry_id, etym.text)
                for audit in info.findall("audit"):
                    upd_date = audit.find("upd_date")
                    upd_detl = audit.find("upd_detl")
                    self.tables["audit"].insert(entry_id, upd_dte, upd_detl)

            # sense
            for sense in entry.findall("sense"):
                # Each sense gets its own ID, for grouping purposes
                sense_id = self.tables["sense"].insert(entry_id)
                for stagk in sense.findall("stagk"):
                    self.tables["stagk"].insert(sense_id, stagk.text)
                for stagr in sense.findall("stagr"):
                    self.tables["stagr"].insert(sense_id, stagr.text)
                for pos in sense.findall("pos"):
                    entity_id = entity_int[pos.text]
                    self.tables["pos"].insert(sense_id, entity_id)
                for xref in sense.findall("xref"):
                    self.tables["xref"].insert(sense_id, xref.text)
                for ant in sense.findall("ant"):
                    self.tables["ant"].insert(sense_id, ant.text)
                for field in sense.findall("field"):
                    entity_id = entity_int[field.text]
                    self.tables["field"].insert(sense_id, entity_id)
                for misc in sense.findall("misc"):
                    entity_id = entity_int[misc.text]
                    self.tables["misc"].insert(sense_id, entity_id)
                for s_inf in sense.findall("s_inf"):
                    self.tables["s_inf"].insert(sense_id, s_inf.text)
                for lsource in sense.findall("lsource"):
                    lang = lsource.get("xml:lang", "eng")
                    ls_type = lsource.get("ls_type")  # implied "full" if absent, "part" otherwise
                    ls_wasei = lsource.get("ls_wasei") # usually "y"... just a flag.

                    partial = 1 if ls_type is not None else 0
                    if ls_wasei is None:
                        wasei = 0
                    elif ls_wasei.text == "y":
                        wasei = 1
                    else:
                        raise ValueError(
                            'Only known valid ls_wasei attribute value '
                            'is "y", found:', ls_wasei.text)

                    self.tables["lsource"].insert(sense_id,
                                                  lang, partial, wasei)
                for dial in sense.findall("dial"):
                    entity_id = entity_int[dial.text]
                    self.tables["dial"].insert(sense_id, entity_id)
                for gloss in sense.findall("gloss"):
                    lang = gloss.get("xml:lang", "eng")
                    g_gend = gloss.get("g_gend")
                    pri_list = gloss.getchildren()
                    if len(pri_list) > 1:
                        gloss_id = self.tables['gloss'].insert(
                            sense_id, lang, g_gend, gloss.text, 1)
                        for pri in pri_list:
                            self.tables['pri'].insert(gloss_id, pri.text)
                    else:
                        self.tables['gloss'].insert(sense_id, lang, g_gend,
                                                    gloss.text, 0)
                        try:
                            out_text = gloss.text.encode("cp932")
                            print("GLOSS DETECTED:", out_text, "|",
                                  lang, g_gend, pri_list)
                        except:
                            print("GLOSS DETECTED (can't decode text):",
                                  repr(gloss.text), "|",
                                  lang, g_gend, pri_list)
                for example in sense.findall("example"):
                    self.tables["example"].insert(sense_id, example.text)

            ########################################

            self.conn.commit()
            print("========================================")

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

    def insert(self, *args):
        """Runs an insert with the specified arguments.

        Returns the row id of the insert.  (cursor.lastrowid)

        """
        query = self._get_insert_query()

        try:
            uni_args = u"(%s)" % u", ".join(
                [unicode(o) for o in args])
            print(query, uni_args)
        except UnicodeEncodeError:
            print("(UnicodeEncodeError)", query, args)

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
    ls_wasei=y/null => wasei=1/0

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
