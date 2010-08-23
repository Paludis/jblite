from __future__ import print_function
from __future__ import with_statement

import sys, gzip, re
from cStringIO import StringIO
from xml.etree.cElementTree import ElementTree


"""
Notes about XML format:

- XML document MUST be well-formed.

- XML document -MAY- be valid if DTD is supplied and document complies
  with the DTD.

Well formed definition:

  1. As a whole, it matches the format (or "production"):

     ( prolog element Misc* ) - (Char* RestrictedChar Char* )

     In English:

     1. prolog portion:
        1. <?xml ...>
        2. Misc elements
        3. Optionally: a doctypedecl followed by more misc elements
     2. Single element: the root
     3. Misc entries after

     Misc entries include: comments, PI (processing instructions), S (spaces)

     So:

     1. <?xml ...> *will* occur first (probably comments WILL fail if
        found before)
     2. Other tags *may* be present after, before the DTD
     3. The DTD *will* be included before the main document (and only
        one is allowed)

     Simply: Read until <!DOCTYPE, parse until ]>.

     REMAINING question: can "]>" occur anywhere else???
"""

"""
More format details:

document
(prolog element Misc*)
((XMLDecl Misc* (doctypedecl Misc*)?) element Misc*)
element: <name attr=1(...) /> OR <name attr=1(...)>...</name>
Misc: Comments, space, or PI
Comments: <!-- comment... -->
PI: <?PITarget dsfjslfjslafjasljlj... ?>
PITarget: Name excluding XML (case-insensitive)

So:
1. <?xml version = "1.1" encoding = "enc_name" standalone = "yes"|"no" ?>
2. comments/PIs/space (multiple)
3. <!DOCTYPE bleh (SYSTEM/PUBLIC ext_id) [intSubset] >
    intSubset ::= markupdecl | DeclSep
    DeclSep ::= PEReference (%bleh;) or space
                (PEReference: Parameter-entity reference)


"""

def get_dtd(xml_data):
    """Gets the DTD from JMdict."""
    # This is not a perfect solution; it assumes we don't use []'s
    # inside the DTD.
    #
    # It would be better to simply have a reliable way to extract the
    # DTD from the doc, then check its entity dictionary...
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
