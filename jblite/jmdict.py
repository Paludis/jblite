# -*- coding: utf-8 -*-
"""JMdict support."""

# This could be a bit cleaner if I used something like SQLalchemy
# perhaps...  The create/insert/index bits were done decent enough,
# but lookups are done in straight SQL due to the potential
# complexity, and this sadly does break the abstraction of the table
# objects...

from __future__ import print_function
from __future__ import with_statement

import os, sys, re, sqlite3
from cStringIO import StringIO
from xml.etree.cElementTree import ElementTree
from helpers import gzread
from table import Table, KeyValueTable

import gettext
#t = gettext.translation("jblite")
#_ = t.ugettext
gettext.install("jblite")

# Full expansion of xml:lang
XML_LANG = "{http://www.w3.org/XML/1998/namespace}lang"


# Copied from kd2.py...
get_encoding = sys.getfilesystemencoding


class Entry(object):

    def __init__(self, data_d):
        self._d = data_d

    def __unicode__(self):
        """Basic string representation of the entry."""
        d = self._d
        lines = []

        k_eles = d.get("k_ele", [])
        if len(k_eles) > 0:
            lines.append(_(u"Kanji readings:"))
        for k_ele_index, k_ele in enumerate(k_eles):
            k_ele_index += 1
            lines.append(_(u"  Reading %d:") % k_ele_index)
            lines.append(_(u"    Blob: %s") % k_ele['keb'])

        r_eles = d.get("r_ele", [])
        if len(r_eles) > 0:
            lines.append(_(u"Kana readings:"))
        for r_ele_index, r_ele in enumerate(r_eles):
            r_ele_index += 1
            lines.append(_(u"  Reading %d:") % r_ele_index)
            lines.append(_(u"    Blob: %s") % r_ele['reb'])

        senses = d.get("sense", [])
        if len(senses) > 0:
            lines.append(_(u"Glosses:"))
        for sense_index, sense in enumerate(senses):
            sense_index += 1
            lines.append(_(u"  Sense %d:") % sense_index)
            glosses = sense.get("gloss", {})
            # Output glosses by language
            for lang in sorted(glosses.keys()):
                values = glosses[lang]
                lines.append(_(u"    Lang: %s") % lang)
                for val_index, val_d in enumerate(values):
                    val_index += 1
                    val = val_d['value']
                    lines.append(_(u"      Gloss %d: %s") % (val_index, val))
        return u"\n".join(lines)

    def __repr__(self):
        return repr(self._d)


class Database(object):

    """Top level object for SQLite 3-based JMdict database."""

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

    def search(self, query, lang=None):
        # Search
        # Two main methods: to and from Japanese.
        # 1. Guess which direction we're searching.
        # 2. Search preferred method.
        # 3. Search remaining method.
        entries_from = self.search_from_japanese(query)
        entries_to = self.search_to_japanese(query, lang=lang)

        results = entries_from + entries_to
        return results

    def search_from_japanese(self, query):
        # Japanese search locations:
        # 1. Kanji elements
        # 2. Reading elements
        # 3. Any indices (none yet)
        #
        # Preferred orderings
        # 1. Location of query in result
        #    1. Exact match
        #    2. Begins with
        #    3. Anywhere
        # 2. Ranking of usage (the (P) option in EDICT, for example)
        #
        # FOR NOW: just get the searching working.
        # This puts us on roughly the same level as J-Ben 1.2.x.
        encoding = get_encoding()
        wrapped_query = "%%%s%%" % query  # Wrap in wildcards
        unicode_query = wrapped_query.decode(encoding)

        entries_by_keb = self._search_keb(unicode_query)
        entries_by_reb = self._search_reb(unicode_query)
        #entries_by_indices = self._search_indices_from_ja(unicode_query)

        # Merge results into one list and return.
        results = []
        for lst in (entries_by_keb, entries_by_reb):
            for o in lst:
                if o not in results:
                    results.append(o)
        return results

    def _search_keb(self, unicode_query):
        """Searches kanji elements (Japanese readings with kanji).

        Returns a list of entry IDs.

        """
        # keb: entry.id -> k_ele.fk, k_ele.value
        query = "SELECT fk FROM k_ele WHERE value LIKE ?"
        args = (unicode_query,)
        self.cursor.execute(query, args)
        rows = self.cursor.fetchall()
        return [row[0] for row in rows]

    def _search_reb(self, unicode_query):
        """Searches reading elements (Japanese readings without kanji).

        Returns a list of entry IDs.

        """
        # reb: entry.id -> r_ele.fk, r_ele.value
        query = "SELECT fk FROM r_ele WHERE value LIKE ?"
        args = (unicode_query,)
        self.cursor.execute(query, args)
        rows = self.cursor.fetchall()
        return [row[0] for row in rows]

    def _search_indices_from_ja(self, unicode_query):
        raise NotImplementedError

    def search_to_japanese(self, query, lang):
        # Foreign language search locations:
        # 1. Glosses
        # 2. Any indices (none yet)
        #
        # For other considerations, see search_from_japanese().
        encoding = get_encoding()
        wrapped_query = "%%%s%%" % query  # Wrap in wildcards
        unicode_query = wrapped_query.decode(encoding)

        entries_by_glosses = self._search_glosses(unicode_query, lang)
        #entries_by_indices = self._search_indices_to_ja(unicode_query, lang)

        # Merge results into one list and return.
        results = []
        for lst in (entries_by_glosses,):
            for o in lst:
                if o not in results:
                    results.append(o)
        return results


    def _search_glosses(self, unicode_query, lang):
        """Searches foreign language glosses.

        If lang is not None, only entries which match the lang
        parameter are returned.

        Returns a list of entry IDs.

        """
        # entry.id -> sense.fk, sense.id -> gloss.fk
        if lang is not None:
            query = (
                "SELECT e.id FROM gloss g, sense s, entry e "
                "WHERE g.lang = ? AND g.value LIKE ? "
                "AND g.fk = s.id AND s.fk = e.id"
            )
            args = (lang, unicode_query)
        else:
            query = (
                "SELECT e.id FROM gloss g, sense s, entry e "
                "WHERE g.value LIKE ?"
            )
            args = (unicode_query,)

        self.cursor.execute(query, args)
        rows = self.cursor.fetchall()
        return [row[0] for row in rows]

    def _search_indices_to_ja(self, unicode_query, lang):
        raise NotImplementedError

    def query_db(self, *args, **kwargs):
        """Helper.  Wraps the execute/fetchall idiom on the DB cursor."""
        self.cursor.execute(*args, **kwargs)
        return self.cursor.fetchall()

    def _convert_entities(self, entities):
        """Expands a list of entities.

        Returns a list of the entity expansions.  The order of the
        returned expansions matches the order of the input entities.

        """
        args = list(sorted(set(entities)))
        template = ", ".join(["?"] * len(args))
        query = "SELECT entity, expansion " \
            "FROM entity WHERE entity IN (%s)" % template
        rows = self.query_db(query, args)
        d = {}
        for entity, expansion in rows:
            d[entity] = expansion
        result = [d[entity] for entity in entities]
        return result

    def lookup(self, entry_id):
        """Creates an entry object.

        Returns an Entry object (a thin layer around a data
        dictionary).

        """
        # Basically, this is the reverse of _populate_database for a
        # single entry.
        #
        # Structure
        # =========
        #
        # entry -> k_ele -> ke_inf
        #                -> ke_pri
        #       -> r_ele -> re_restr
        #                -> re_inf
        #                -> re_pri
        #       -> links
        #       -> bibl
        #       -> etym
        #       -> audit
        #       -> sense -> (pos, field, misc, dial, stagk, stagr,
        #                    xref, ant, s_inf, example, lsource)
        #                -> gloss -> pri

        result = {}

        # AT LEAST (for now...):
        # 1. readings
        # 1.1. k_ele
        query = "SELECT id, value FROM k_ele WHERE fk = ?"
        args = (entry_id,)
        rows = self.query_db(query, args)
        k_ele = []
        for k_ele_id, keb in rows:
            # ke_inf
            query = "SELECT entity FROM ke_inf WHERE fk = ?"
            args = (k_ele_id,)
            rows = self.query_db(query, args)
            ke_inf = self._convert_entities([row[0] for row in rows])

            # ke_pri
            query = "SELECT value FROM ke_pri WHERE fk = ?"
            args = (k_ele_id,)
            rows = self.query_db(query, args)
            ke_pri = [row[0] for row in rows]

            # merge results
            k_ele_d = {}
            k_ele_d['keb'] = keb
            k_ele_d['ke_pri'] = ke_pri
            k_ele_d['ke_inf'] = ke_inf
            k_ele.append(k_ele_d)
        result['k_ele'] = k_ele
        # 1.2. r_ele
        query = "SELECT id, value, nokanji FROM r_ele WHERE fk = ?"
        args = (entry_id,)
        rows = self.query_db(query, args)
        r_ele = []
        for r_ele_id, reb, nokanji in rows:
            # re_restr
            query = "SELECT value FROM re_restr WHERE fk = ?"
            args = (r_ele_id,)
            rows = self.query_db(query, args)
            re_restr = [row[0] for row in rows]

            # re_inf
            query = "SELECT entity FROM re_inf WHERE fk = ?"
            args = (r_ele_id,)
            rows = self.query_db(query, args)
            re_inf = self._convert_entities([row[0] for row in rows])

            # re_pri
            query = "SELECT value FROM re_pri WHERE fk = ?"
            args = (r_ele_id,)
            rows = self.query_db(query, args)
            re_pri = [row[0] for row in rows]

            # merge results
            r_ele_d = {}
            r_ele_d['reb'] = reb
            r_ele_d['nokanji'] = True if nokanji == 1 else False
            r_ele_d['re_restr'] = re_restr
            r_ele_d['re_pri'] = re_pri
            r_ele_d['re_inf'] = re_inf
            r_ele.append(r_ele_d)
        result['r_ele'] = r_ele

        # 2. glosses
        query = "SELECT id FROM sense WHERE fk = ?"
        args = (entry_id,)
        rows = self.query_db(query, args)
        sense_ids = [row[0] for row in rows]

        sense = []
        for sense_id in sense_ids:
            # gloss
            query = "SELECT lang, value, g_gend, pri FROM gloss WHERE fk = ?"
            args = (sense_id,)
            rows = self.query_db(query, args)
            gloss = {}
            for lang, value, g_gend, pri in rows:
                lst = gloss.setdefault(lang, [])
                lst.append(
                    {"value": value, "g_gend": g_gend, "pri": pri})
            sense_d = {}
            sense_d['gloss'] = gloss
            sense.append(sense_d)
        result['sense'] = sense

        return Entry(result)

    def _create_table_objects(self):
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
            "entity": EntityTable,   # Info from JMdict XML entities
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
        entity_int_d = {}
        tbl = self.tables['entity']
        for entity, expansion in entities.iteritems():
            i = tbl.insert(entity, expansion)
            entity_int_d[expansion] = i

        # Iterate through each entry
        for entry in etree.findall("entry"):

            # entry table
            ent_seq = entry.find("ent_seq")
            entry_id = self.tables["entry"].insert(int(ent_seq.text))

            for k_ele in entry.findall("k_ele"):
                # k_ele
                value = k_ele.find("keb").text
                k_ele_id = self.tables["k_ele"].insert(entry_id, value)

                # ke_inf
                for ke_inf in k_ele.findall("ke_inf"):
                    value = ke_inf.text.strip()
                    entity_id = entity_int_d[value]
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
                    value = re_inf.text.strip()
                    entity_id = entity_int_d[value]
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
                    link_tag = links.find("link_tag").text
                    link_desc = links.find("link_desc").text
                    link_uri = links.find("link_uri").text
                    self.tables["links"].insert(entry_id, link_tag, link_desc,
                                                link_uri)
                for bibl in info.findall("bibl"):
                    bib_tag = links.find("bib_tag")
                    bib_txt = links.find("bib_txt")
                    bib_tag = bib_tag.text if bib_tag is not None else None
                    bib_txt = bib_txt.text if bib_txt is not None else None
                    self.tables["bibl"].insert(entry_id, bib_tag, bib_txt)
                for etym in info.findall("etym"):
                    self.tables["etym"].insert(entry_id, etym.text)
                for audit in info.findall("audit"):
                    upd_date = audit.find("upd_date").text
                    upd_detl = audit.find("upd_detl").text
                    self.tables["audit"].insert(entry_id, upd_date, upd_detl)

            # sense
            key_entity_tables = ["pos", "field", "misc", "dial"]
            key_value_tables = ["stagk", "stagr", "xref", "ant", "s_inf", "example"]

            for sense in entry.findall("sense"):
                # Each sense gets its own ID, for grouping purposes
                sense_id = self.tables["sense"].insert(entry_id)

                for elem_name in key_value_tables:
                    for element in sense.findall(elem_name):
                        self.tables[elem_name].insert(sense_id, element.text)

                for elem_name in key_entity_tables:
                    for element in sense.findall(elem_name):
                        entity_id = entity_int_d[element.text.strip()]
                        self.tables[elem_name].insert(sense_id, entity_id)

                for lsource in sense.findall("lsource"):
                    lang = lsource.get(XML_LANG, "eng")
                    ls_type = lsource.get("ls_type")  # implied "full" if absent, "part" otherwise
                    ls_wasei = lsource.get("ls_wasei") # usually "y"... just a flag.

                    partial = 1 if ls_type is not None else 0
                    if ls_wasei is None:
                        wasei = 0
                    elif ls_wasei == "y":
                        wasei = 1
                    else:
                        raise ValueError(
                            'Only known valid ls_wasei attribute value '
                            'is "y", found:', ls_wasei.text)

                    self.tables["lsource"].insert(sense_id,
                                                  lang, partial, wasei)
                for gloss in sense.findall("gloss"):
                    lang = gloss.get(XML_LANG, "eng")
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

    def _get_entities(self, xml_data):
        """Gets the ENTITY definitions from JMdict.

        Finds the built-in DTD and extracts all ENTITY definitions.

        """
        dtd = self._get_dtd(xml_data)
        # do some logic to find all entities...
        entities = {}
        regex = '<!ENTITY[ ]+([a-zA-Z0-9-]+)[ ]+"(.*?)">'
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


class EntryTable(Table):
    create_query = ("CREATE TABLE %s "
                    "(id INTEGER PRIMARY KEY, ent_seq INTEGER)")
    insert_query = "INSERT INTO %s VALUES (NULL, ?)"
    index_queries = [
        "CREATE INDEX %s_seq ON %s (ent_seq)",
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

def parse_args():
    from optparse import OptionParser
    op = OptionParser(usage="%prog [options] <db_filename> [search_query]")
    op.add_option("-i", "--initialize",
                  dest="init_fname", metavar="XML_SOURCE",
                  help=_("Initialize database from file."))
    op.add_option("-L", "--lang",
                  help=_("Specify preferred language for searching."))
    options, args = op.parse_args()
    if len(args) < 1:
        op.print_help()
        exit(-1)
    return (options, args)

def main():
    # Copied *almost* verbatim from kd2.py.
    options, args = parse_args()
    db_fname = args[0]

    if options.init_fname is not None:
        db = Database(db_fname, init_from_file=options.init_fname)
    else:
        db = Database(db_fname)

    results = []
    if len(args) > 1:
        # Do search
        # To be nice, we'll join all remaining args with spaces.
        search_query = " ".join(args[1:])
        if options.lang is not None:
            results = db.search(search_query, lang=options.lang)
        else:
            results = db.search(search_query)

    if len(results) > 0:
        from pprint import pprint
        encoding = get_encoding()
        for index, result in enumerate(results):
            index += 1
            print(_("[Entry %d]") % index)
            entry = db.lookup(result)
            try:
                print(unicode(entry).encode(encoding))
            except:
                print(repr(entry))
            print()
    else:
        print(_("No results found."))

if __name__ == "__main__":
    main()
