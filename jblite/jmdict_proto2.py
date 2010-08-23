from __future__ import print_function
from __future__ import with_statement

import sys, gzip, re
from cStringIO import StringIO
from xml.etree.cElementTree import ElementTree


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
