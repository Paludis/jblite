=============================
 JBLite Design Documentation
=============================

JMdict
======

Database object API
-------------------

1. __init__(filename, init_from_file=None, init_method="etree")

   - Encapsulates an SQLite 3 database
   - Default: specify SQLite 3 DB file name
   - Alternative: Specify init_from_file to create a new SQLite
     database based upon a source file.  (File must be in Jim Breen's
     JMdict XML format, in its default UTF-8 encoding.  However,
     either the gzipped or uncompressed version may be used.)

     - Extra arg: init_method.  Default is "etree", which uses
       CElementTree to quickly import and create a database.

       A low memory alternative implementation using SAX or similar
       may be provided, although this is known to be painfully slow...
       If this is done, it may be better to make a C extension for
       this logic...

2. search(query, pref_lang=None)

   - single API to handle searches of both Japanese and foreign
     language glosses.
   - pref_lang determines the "foreign" language to search.  None
     means search all.  Known values will be "en" and "fr".  Maybe
     "es(?)" (Spanish) and "??" (German) as well...?


Entry API
---------

What do we want to query as-needed?

- keb/reb/glosses as main
- other...


Object design
-------------

::

  Database
   |
   +- Tables
       +- EntityTable (XML entity lookup, to save space)
       +- 1-M mapping tables
       +- Misc. tables.... generalized if possible, specialized if must

Database design ideas:

- Database creates all needed tables from an XML file.
- Search function knows which tables to query to find entries.
- On a search match, the code will find the root node which owns the
  gloss in question.  (This means code specific to each match, since
  we got to walk back through the tables to find the original
  entry...)
- Optimization: For any tables we want to be "searchable", add an
  extra column with the entry ID.  It's data duplication, but it keeps
  us from having to read 5+ tables to find the entry key.

Database object ideas:

- Optimization: For any given attribute: the first access reads it
  from the DB, the following accesses use the cached value.  Assumes
  the DB does not change in real time; a fair constraint on a single
  user study application.

  - More than one value may be read at a time in some cases... maybe?
  - Premature optimization?  Standard use may be to grab all data
    regardless...


KANJIDIC2
=========

Databse object API
------------------

1. __init__(filename, init_from_file=None, init_method="etree")

   - Encapsulates an SQLite 3 database
   - Default: specify SQLite 3 DB file name
   - Alternative: Specify init_from_file to create a new SQLite
     database based upon a source file.  (File must be in Jim Breen's
     JMdict XML format, in its default UTF-8 encoding.  However,
     either the gzipped or uncompressed version may be used.)

     - Extra arg: init_method.  Default is "etree", which uses
       CElementTree to quickly import and create a database.

       A low memory alternative implementation using SAX or similar
       may be provided, although this is known to be painfully slow...
       If this is done, it may be better to make a C extension for
       this logic...

2. search(query)

   - query is a Japanese string containing one or more kanji.

3. query_code_search(query_type, query)

   - Allows use of SKIP, De Roo, Four Corners and S&H query code
     systems to look up kanji.

4. stroke_count_search(count, allow_miscounts=False, error_margin=0,
                       error_margin_type="plusminus")

   - Query by stroke count
   - On allow_miscounts: include common miscounts as candidates
   - error_margin allows minor miscounts on all candidates.
   - error_margin_type selects the type of margin: "plus", "minus", or
     "plusminus".

5. stroke_count_filter(candidates, count, allow_miscounts=False,
                       error_margin=0, error_margin_type="plusminus")

   - Takes a list of candidates, filters them by count.  Database is
     only hit if necessary.
   - All other args are like stroke_count_search.

Low priority:

6. dict_code_lookup(dict_name, dict_code)

   - Takes a dictionary ID code and a dictionary code, returns a
     kanji.
   - Really limited use case... probably won't implement this.


Entry API
---------

What do we want to query as-needed?

- readings (on/kun)
- nanori
- meanings (en/es/fr/etc)
- stroke count
- dict codes
- query codes
- lots of misc. info
