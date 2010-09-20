===========================
 KANJIDIC2 Database Schema
===========================

Original XML Schema
===================

::

  kanjidic2
  - header
    - file_version
    - database_version
    - date_of_creation
  * character   # what is meaning of * after list of child elements?  (a, b, c, ...)*
    - literal
    - codepoint
      + cp_value
    - radical
      + rad_value
    - misc
      ? grade
      + stroke_count
      + variant
      ? freq
      * rad_name
      ? jlpt
    ? dic_number
      + dic_ref
    ? query_code
      + q_code
    ? reading_meaning
      * rmgroup
        * reading
        * meaning
      * nanori

SQLite3 Schema
==============

CREATE TABLE header (file_version TEXT, database_version TEXT, date_of_creation TEXT);

character: -> CharacterTable
  id INTEGER, literal TEXT, grade INTEGER, freq INTEGER, jlpt INTEGER

codepoint, radical, variant: -> TypeValueTable
  id INTEGER, fk INTEGER, type TEXT, value TEXT

stroke_count: -> StrokeCountTable
  id INTEGER, fk INTEGER, count INTEGER

rad_name, nanori: -> KeyValueTable
  id INTEGER, fk INTEGER, value TEXT

dic_number:  (First revision)
  id INTEGER, fk INTEGER, type TEXT, m_vol TEXT, m_page TEXT
  - Might remove moro pieces and put in separate table to save space...
  - Alternatively could merge m_vol/m_page into the moro code directly

query_code:
  id INTEGER, fk INTEGER, type TEXT, skip_misclass TEXT, value TEXT
  - Might move skip miscodes into a separate table...
  - Might re-code SKIP values separately based upon integers... but
    the same could be argued about all other codes...  probably
    shouldn't waste time on this.

rmgroup:
  id INTEGER, fk INTEGER

reading:
  id INTEGER, fk INTEGER, type TEXT, on_type TEXT, r_status TEXT, value TEXT

meaning:
  id INTEGER, fk INTEGER, lang TEXT, value TEXT
