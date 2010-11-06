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

      CREATE INDEX %s_XXX ON %s (YYY)"

    where %s is a placeholder for the table name (note that it's used
    twice), and XXX/YYY are replaced as desired.

    """

    create_query = None
    insert_query = None
    index_queries = []

    def __init__(self, cursor, table_name):
        self.cursor = cursor
        self.table_name = table_name

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


class KeyValueTable(Table):
    """General key/value table for one-many relations."""
    create_query = ("CREATE TABLE %s "
                    "(id INTEGER PRIMARY KEY, fk INTEGER, value TEXT)")
    insert_query = "INSERT INTO %s VALUES (NULL, ?, ?)"
    index_queries = [
        "CREATE INDEX %s_fk ON %s (fk)",
        ]
