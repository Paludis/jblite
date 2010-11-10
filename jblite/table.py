# -*- coding: utf-8 -*-

from pprint import pformat


class Record(object):

    """Represents a row in a table, plus all data it is a 'parent' of.

    Each Record may be linked to multiple Records in child tables.

    """

    def __init__(self, data=None, children=None):
        self.data = data if data is not None else {}
        self.children = children if children is not None else {}

    def as_dict(self):
        """Returns a dictionary representing the values in the record."""
        data_d = {}
        for key in self.data.keys():
            data_d[key] = self.data[key]
        children_d = {}
        for table, records in self.children.iteritems():
            children_d[table] = [record.as_dict() for record in records]
        result_d = {}
        if len(data_d) > 0:
            result_d[u"data"] = data_d
        if len(children_d) > 0:
            result_d[u"children"] = children_d
        return result_d

    def find_children(self, *args):
        """Returns child records for the given string arguments.

        Each argument is used as a key for selecting a group out of
        the next generation of child objects.  For example, the args
        ["sense", "gloss"] will return a list of all gloss records.

        Returns a list of records, or an empty list if none are found.

        """
        records = [self]
        for key in args:
            record_lists = [record.children.get(key, []) for record in records]
            # Merge the lists into one.
            records = reduce(lambda x, y: x + y, record_lists)
        return records

    def __unicode__(self):
        return pformat(self.as_dict())

    __repr__ = __unicode__


class Table(object):

    """Base class for tables.

    Given SQL template queries, provides table create/insert logic and
    attaches indices if desired.

    create_query and insert_query must be specified in child classes.
    index_queries is not required.

    create_query and insert_query take a single template argument: the
    table name.  Do not put the table name in directly; replace it
    with %s.

    index_queries are a little more complicated.  They should be
    specified like so:

      CREATE INDEX %s_XXX ON %s (YYY)

    where %s is a placeholder for the table name (note that it's used
    twice), and XXX/YYY are replaced as desired.

    """

    create_query = None
    insert_query = None
    index_queries = []

    def __init__(self, cursor, name):
        self.cursor = cursor
        self.name = name

    def create(self):
        """Creates table, plus indices if supplied in class definition."""
        query = self._get_create_query()
        #print(query)
        self.cursor.execute(query)
        index_queries = self._get_index_queries()
        for query in index_queries:
            #print(query)
            self.cursor.execute(query)

    def insert(self, *args):
        """Runs an insert with the specified arguments.

        Returns the row id of the insert.  (cursor.lastrowid)

        """
        query = self._get_insert_query()

        try:
            self.cursor.execute(query, args)
        except:
            print("Exception occurred on insert: query=%s, args=%s" %
                  (repr(query), repr(args)))
            raise
        return self.cursor.lastrowid

    def insertmany(self, *args):
        """Runs a multi-row insert with the specified arguments.

        Arguments are treated similarly to the DB-API 2.0 executemany
        statement: this function takes a list of argument lists.

        There is no return value.

        """
        query = self._get_insert_query()
        try:
            self.cursor.executemany(query, *args)
        except:
            print("Exception occurred on insertmany: query=%s, args=%s" %
                  (repr(query), repr(args)))
            raise

    def _get_create_query(self):
        if self.name is None:
            raise ValueError(
                "name must be specified in class definition")
        return self.create_query % self.name

    def _get_insert_query(self):
        if self.name is None:
            raise ValueError(
                "name must be specified in class definition")
        return self.insert_query % self.name

    def _get_index_queries(self):
        if self.name is None:
            raise ValueError(
                "name must be specified in class definition")
        if (not (isinstance(self.index_queries, list))
          or (len(self.index_queries) == 0)):
            return []
        else:
            # Each query needs to have the table name merged in two
            # places.
            queries = [q % (self.name, self.name)
                       for q in self.index_queries]
            return queries

    def lookup_by_id(self, id):
        """Retrieves the row matching the id.

        Returns the matching row, or None if no row was found.

        """
        query = "SELECT * FROM %s WHERE id = ?" % self.name
        self.cursor.execute(query, (id,))
        row = self.cursor.fetchone()
        return row


class ChildTable(Table):

    """Table using a foreign key column for parent-child relationships."""

    def lookup_by_fk(self, fk):
        """Retrieves all rows with the matching foreign key.

        Returns a list of rows.  If no rows are found, an empty list
        is returned.

        """
        query = "SELECT * FROM %s WHERE fk = ?" % self.name
        self.cursor.execute(query, (fk,))
        rows = self.cursor.fetchall()
        return rows


class KeyValueTable(ChildTable):
    """General key/value table for one-many relations."""
    create_query = ("CREATE TABLE %s "
                    "(id INTEGER PRIMARY KEY, fk INTEGER, value TEXT)")
    insert_query = "INSERT INTO %s VALUES (NULL, ?, ?)"
    index_queries = [
        "CREATE INDEX %s_fk ON %s (fk)",
        ]
