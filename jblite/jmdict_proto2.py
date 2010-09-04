from __future__ import print_function
from __future__ import with_statement

import sys, gzip, re
from cStringIO import StringIO
from xml.etree.cElementTree import ElementTree


"""
$ grep -e '&.*;' JMdict | grep -v -e '&lt;' -e '&gt;' -e '&nbsp;' -e '&amp;' | sort | uniq | grep -oe '^<[^>]*>' | uniq
<dial>
<field>
<ke_inf>
<misc>
<pos>
<re_inf>
"""



class Table(object):

    """Base class for tables."""

    # These queries must be specified in child classes.
    table_name = None
    create_query = None
    insert_query = None
    index_queries = []

    def __init__(self, cursor):
        self.cursor = cursor
        self.__next_id = 1

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
            queries = [q % self.table_name for q in self.index_queries]
            return queries


class AutoIncrementTable(Table):

    """Auto-increment table base class."""

    def __init__(self, cursor):
        Table.__init__(self, cursor)
        self.__next_id = 1

    def insert(self, *args):
        i = self._get_id()
        query_args = [i] + args
        try:
            self.cursor.execute(self._get_insert_query(),
                                query_args)
        except Exception, e:
            self._rollback_id()
            raise e

    def _get_id(self):
        """Gets next auto-increment ID."""
        result = self.next_id
        self.__next_id += 1
        return result

    def _rollback_id(self):
        """Rolls back ID (in case of errors)"""
        self.__next_id -= 1

    def _peek_next_id(self):
        """Currently unused."""
        # Here only to complete the API.
        return self.__next_id


class EntityRefTable(AutoIncrementTable):
    # Used for: ke_inf, re_inf, dial, 3 others...
    table_name = None
    # i = auto-inc, fk = foreign key, entity = value
    create_query = "CREATE TABLE %s (i INTEGER, fk INTEGER, entity INTEGER)"
    insert_query = "INSERT INTO %s VALUES (?, ?, ?)"
    index_queries = [
        "CREATE INDEX fk_index ON %s (fk)",
        ]

# ----- Real tables follow -----

class KeInfTable(EntityRefTable):
    table_name = "ke_inf"
class ReInfTable(EntityRefTable):
    table_name = "re_inf"
class DialectTable(EntityRefTable):
    table_name = "dial"


class EntityTable(AutoIncrementTable):
    table_name = "entities"
    create_query = "CREATE TABLE %s (i INTEGER, entity TEXT, expansion TEXT)"
    insert_query = "INSERT INTO %s VALUES (?, ?, ?)"
    index_queries = [
        "CREATE INDEX entity_index ON %s (entity)",
        ]



def get_dtd(xml_data):
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

def get_entities(xml_data):
    """Gets the ENTITY definitions from JMdict.

    Finds the built-in DTD and extracts all ENTITY definitions.

    """
    dtd = get_dtd(xml_data)
    # do some logic to find all entities...
    entities = {}
    regex = "<!ENTITY[ ]+([a-zA-Z-]+)[ ]+['\"](.*?)['\"]>"
    for match in re.finditer(regex, xml_data):
        key, value = match.groups()[0:2]
        key = "&%s;" % key  # Convert to &entity; format
        entities[key] = value
    return entities

def gzread(fname):
    try:
        infile = gzip.open(sys.argv[1])
        data = infile.read()
        infile.close()
    except IOError, e:
        if e.args[0] == "Not a gzipped file":
            with open(sys.argv[1]) as infile:
                data = infile.read()
        else:
            raise e
    return data

def parse_file(fname):
    """Loads file (gzipped or not) and returns parsed data.

    Result is a two-item tuple: (ElementTree, entities (dict))

    """
    raw_data = gzread(fname)
    entities = get_entities(raw_data)
    infile = StringIO(raw_data)
    etree = ElementTree(file=infile)
    infile.close()
    return (etree, entities)

def main():
    entities, etree = parse_file(sys.argv[1])

if __name__ == "__main__":
    main()
