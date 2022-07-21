import sys
import os
import re

from egazette.us.states.resolver import RefResolver
from egazette.us.states.akn import Akn30


if __name__ == '__main__':
    indir    = sys.argv[1]
    outdir   = sys.argv[2]
    mediaurl = sys.argv[3]

    akn30 = Akn30(mediaurl)
    regulations = {}

    for filename in os.listdir(indir):
        #if filename != 'oh-2022-admin-0125.00.xml':
        #    continue

        if re.search('\.swp$', filename):
            continue

        filepath = os.path.join(indir, filename)
        if os.path.isfile(filepath):
            akn30.process_casemaker(filepath, regulations)

    refresolver = RefResolver()
    for num, regulation in regulations.items():
        if num == None:
            continue

        refresolver.add_regulation(regulation) 

    #for k, v in refresolver.refids.items():
    #    print ('REF', k, v)

    for num, regulation in regulations.items():
        if num == None:
            continue

        refresolver.resolve(regulation)    

    for num, regulation in regulations.items():
        if num == None:
            continue

        filepath = os.path.join(outdir, '%s.xml' % num)
        regulation.write_akn_xml(filepath)
    
