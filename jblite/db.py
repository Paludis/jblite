"""Base database object support."""

from table import Record


class Database(object):

    entry_class = None
    table_map = None

    def __init__(self):
        self.tables = {}

    def lookup(self, key, entry_id):
        """Creates an entry object.

        Finds a record table based upon the entry table.  (This
        contains all data for an entry.)  This is then wrapped in an
        Entry object which provides logic for displaying or otherwise
        using the data.

        """
        # Lookup data in entry table.
        data = self.tables[key].lookup_by_id(entry_id)  # 1 row only
        # Lookup child data using the entry_id as a foreign key.
        children = self._lookup_children(self.table_map[key], data['id'])
        record = Record(data, children)
        return self.entry_class(record)

    def _lookup_children(self, children_map, fk):
        children = {}
        for child_table in children_map:
            grandchild_map = children_map[child_table]
            rows = self._lookup_by_fk(child_table,
                                      children_map[child_table], fk)
            if len(rows) > 0:
                children[child_table] = rows
        return children

    def _lookup_by_fk(self, table_name, children_map, fk):
        """Looks up data from a table and related 'child' tables.

        table_name: name of the table to query.
        children_map: a dictionary of child table mappings, or None if
            no children are present.
        fk: foreign key used in table query.

        """
        rows = self.tables[table_name].lookup_by_fk(fk)
        results = []
        for row in rows:
            children = self._lookup_children(children_map, row['id'])
            record = Record(row, children)
            results.append(record)
        return results
