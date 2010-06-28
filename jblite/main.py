#!/usr/bin/env python

"""Script for converting KANJIDIC2 to SQLite."""

import optparse
from jblite.kd2 import KD2Converter
from jblite.jmdict import JMdictConverter
import gettext
gettext.install("jblite")


def parse_args():
    usage="usage: %prog [options] <xml_src> <sqlite_dest>"
    op = optparse.OptionParser(usage)
    op.add_option("-v", "--verbose", action="store_true",
                  help=_("Display verbose output (default: %default)"))
    op.add_option("-f", "--format",
                  help=_("Format of database file (kanjidic2, jmdict) "
                         "(default: %default)"))
    op.set_defaults(verbose=False,
                    format="kanjidic2")
    return op.parse_args()

def main():
    (options, args) = parse_args()
    src_fname, dest_fname = args[:2]
    formats = {
        "kanjidic2": KD2Converter,
        "jmdict": JMdictConverter,
        }
    cls = formats[options.format]
    converter = cls(src_fname, dest_fname, verbose=options.verbose)
    converter.run()

if __name__ == "__main__":
    main()
