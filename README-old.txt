jblite: J-Ben SQLite parsing scripts
Copyright 2010 by Paul Goins
Released under the two-clause OSI-approved BSD license (see COPYING.txt)

This library allows conversion of KANJIDIC2.xml into an SQLite
database.  All "data" within KANJIDIC2 (that is, everything except
comments) should be preserved in the SQLite format.

A converter for JMdict will follow in the near future.

No standalone documentation yet exists.  Basically, running the script
goes something like this:

  ./script.py <input_dict.xml> <sqlite_output.db>
