#!/usr/bin/env python

"""Script for converting KANJIDIC2 to SQLite."""

import optparse
from jblite.kd2 import KD2Converter
import gettext
gettext.install("jblite")


def parse_args():
    op = optparse.OptionParser()
    op.usage = "%prog <xml_src> <sqlite_dest>"
    op.add_option("-v", "--verbose", action="store_true",
                  help=_("Display verbose output (default: %default)"))
    op.set_defaults(verbose=False)
    return op.parse_args()

def main():
    (options, args) = parse_args()
    kd2_fname = args[0]
    db_fname = args[1]
    converter = KD2Converter(kd2_fname, db_fname, options.verbose)
    converter.run()

if __name__ == "__main__":
    main()
