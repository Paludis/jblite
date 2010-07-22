import warnings
from lxml import etree


# lxml normalizes XML namespaces... so for xml:lang, we use the
# following constant.
XML_LANG = '{http://www.w3.org/XML/1998/namespace}lang'  # xml:lang


def skip_elem(elem_name):
    warnings.warn("Encountered unsuppored element <%s>.  "
                  "<%s> elements will be skipped." % (elem_name, elem_name))

def main():
    parser = etree.XMLParser(resolve_entities=False)
    import sys
    with open(sys.argv[1]) as infile:
        et = etree.ElementTree(file=infile, parser=parser)
    root = et.getroot()
    for child in root.iterchildren():
        ent_seq = int(child.find('ent_seq').text)
        for k_ele in child.iterfind('k_ele'):
            blob = k_ele.find('keb').text
            #print u"k_ele.keb:", blob
            for ke_inf in k_ele.iterfind('ke_inf'):
                info = ke_inf.text
                #print u"k_ele.ke_inf:", info
            for ke_pri in k_ele.iterfind('ke_pri'):
                priority = ke_pri.text
                #print u"k_ele.ke_pri:", priority
        for r_ele in child.iterfind('r_ele'):
            blob = r_ele.find('reb').text
            #print u"r_ele.reb:", blob
            nokanji = True if r_ele.find('re_nokanji') is not None \
                      else False
            #print u"r_ele.nokanji:", nokanji
            for re_restr in r_ele.iterfind('re_restr'):
                restr = re_restr.text
                #print u"r_ele.re_restr:", restr
            for re_inf in r_ele.iterfind('re_inf'):
                info = re_inf.text
                #print u"r_ele.re_inf:", info
            for re_pri in r_ele.iterfind('re_pri'):
                priority = re_pri.text
                #print u"r_ele.re_pri:", priority
        info = child.find('info')
        if info is not None:
            for links in info.iterfind('links'):
                tag = links.find('link_tag').text
                desc = links.find('link_desc').text
                uri = links.find('link_uri').text
                # do something...
            for bibl in info.iterfind('bibl'):
                tag = bibl.find('bib_tag')
                txt = bibl.find('bib_txt')
                tag = tag.text if tag is not None else None
                txt = txt.text if txt is not None else None
                # do something
            for etym in info.iterfind('etym'):
                # Not yet supported: if we ever encounter, warn.
                skip_elem('etym')
            for audit in info.iterfind('audit'):
                upd_date = audit.find('upd_date').text
                upd_detl = audit.find('upd_detl').text
                # do something...
        for sense in child.iterfind('sense'):
            for stagk in sense.iterfind('stagk'):
                text = stagk.text
                # do something...
            for stagr in sense.iterfind('stagr'):
                text = stagr.text
                # do something...
            for pos in sense.iterfind('pos'):
                text = pos.text  # entity, right...?
                # do something...
            for xref in sense.iterfind('xref'):
                text = xref.text  # text w/ special format; just store for now
                # do something...
            for ant in sense.iterfind('ant'):
                text = ant.text
                # do something...
            for field in sense.iterfind('field'):
                text = field.text
                # do something...
            for misc in sense.iterfind('misc'):
                text = misc.text
                # do something...
            for s_inf in sense.iterfind('s_inf'):
                text = s_inf.text
                # do something...
            for lsource in sense.iterfind('lsource'):
                text = lsource.text
                lang = lsource.get(XML_LANG)
                ltype = lsource.get('ls_type')
                wasei = lsource.get('ls_wasei')
                # do something...
            for dial in sense.iterfind('dial'):
                text = dial.text
                # do something...
            for gloss in sense.iterfind('gloss'):
                lang = gloss.get(XML_LANG)
                gender = gloss.get('g_gend')
                text = gloss.text
                # Do something...
                for pri in gloss.iterfind('pri'):
                    # Not yet supported: if we ever encounter, warn.
                    skip_elem('pri')
            for example in sense.iterfind('example'):
                text = example.text

if __name__ == "__main__":
    main()
