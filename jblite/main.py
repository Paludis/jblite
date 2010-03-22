#!/usr/bin/env python

import optparse
from jblite.kd2 import KD2Converter

def parse_args():
    op = optparse.OptionParser()
    op.add_option("-i", "--interface",
                  help=_("Select interface: gtk, console (default: %default)"))
    op.set_defaults(interface="gtk")
    return op.parse_args()

def main():
    (options, args) = parse_args()
    kd2_fname = args[0]
    db_fname = args[1]
    converter = KD2Converter(kd2_fname, db_fname)
    converter.run()

if __name__ == "__main__":
    main()
