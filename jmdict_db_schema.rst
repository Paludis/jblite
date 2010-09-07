==================
 JMdict DB Schema
==================

Original JMdict XML format (summarized)
=======================================

::

  Entry
    - ent_seq
    * k_ele
      - keb
      * ke_inf
      * ke_pri
    + r_ele
      - reb
      ? re_nokanji
      * re_restr
      * re_inf
      * re_pri
    ? info
      * links
        - link_tag
        - link_desc
        - link_uri
      * bibl
        ? bib_tag
        ? bib_txt
      * etym (UNUSED)
      * audit
        - upd_date
        - upd_detl
    + sense
      * stagk
      * stagr
      * pos
      * xref*  # not sure why it's (#PCDATA)*...
      * ant*   # not sure why it's (#PCDATA)*...
      * field
      * misc
      * s_inf
      * lsource
      * dial
      * gloss
        * pri (UNUSED)
      * example

Description of JMdict SQLite database design
============================================

Basically, the table structure of the SQLite 3 database follows this
very closely.  Here's generally how it's designed:

1. All tables (except entry) have two integer keys, always named id
   and fk.  id is an auto-increment value, while fk is used for
   joining tables.  (fk is of course indexed.)

2. Any data with a one-to-one relationship with a parent XML node was
   moved into a column for the parent node's table.  (Example: <keb>
   is now k_ele.value.)

3. Attributes have similar but usually different names than in JMdict.
   Generally speaking, if an attribute had a prefix (like xml:lang or
   ls_wasei), it is stored without it (as lang or wasei).

4. Info nodes have a one-to-one relationship with entries, so there's
   no table for them.  XML children of the <info> element are linked
   directly to the entry table rather than to a meaningless
   intermediate table.

Examples
========

Example 1: 魚 (entry 1578010)

::

  SELECT * FROM entry
  LEFT JOIN k_ele ON entry.id = k_ele.fk
  LEFT JOIN ke_inf ON k_ele.id = ke_inf.fk
  LEFT JOIN ke_pri ON k_ele.id = ke_pri.fk
  WHERE entry.ent_seq = 1578010

Result:

========  =============  ========  ========  ===========  =========  =========  =============  =========  =========  ============
entry.id  entry.ent_seq  k_ele.id  k_ele.fk  k_ele.value  ke_inf.id  ke_inf.fk  ke_inf.entity  ke_pri.id  ke_pri.fk  ke_pri.value
========  =============  ========  ========  ===========  =========  =========  =============  =========  =========  ============
55777     1578010        48939     55777     魚           None       None       None           42889      48939      ichi1
55777     1578010        48939     55777     魚           None       None       None           42890      48939      ichi2
55777     1578010        48939     55777     魚           None       None       None           42891      48939      news1
55777     1578010        48939     55777     魚           None       None       None           42892      48939      nf03
========  =============  ========  ========  ===========  =========  =========  =============  =========  =========  ============
