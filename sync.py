import datetime
import sys
import os
import logging
import getopt
import re

from egazette.utils import utils
from egazette.utils import download
from egazette.utils.file_storage import FileManager
from egazette.srcs import datasrcs

def print_usage(progname):
    print('''Usage: %s [-l loglevel(critical, error, warn, info, debug)]
                       [-a (all_downloads)]
                       [-m (updateMeta)]
                       [-n (no aggregation of srcs by hostname)]
                       [-r (updateRaw)]
                       [-f logfile]
                       [-t fromdate (DD-MM-YYYY)] [-T todate (DD-MM-YYYY)]
                       [-d last_n_days]
                       [-D datadir]
                       [-s central_weekly -s central_extraordinary -s central
                        -s states 
                        -s andhra -s andhraarchive 
                        -s bihar 
                        -s chattisgarh -s cgweekly -s cgextraordinary 
                        -s delhi -s delhi_weekly -s delhi_extraordinary
                        -s karnataka
                        -s maharashtra -s telangana   -s tamilnadu
                        -s jharkhand   -s odisha      -s madhyapradesh
                        -s punjab      -s uttarakhand -s himachal
                        -s haryana     -s kerala      -s haryanaarchive
                        -s stgeorge    -s himachal    -s keralalibrary
                       ]
                       ''' % progname)

    print('The program will download gazettes from various egazette sites')
    print('and will place in a specified directory. Gazettes will be')
    print('placed into directories named by type and date. If fromdate or')
    print('todate is not specified then the default is your current date.')

def to_datetime(datestr):
    numlist = re.findall('\d+', datestr)
    if len(numlist) != 3:
        print('%s not in correct format [DD/MM/YYYY]' % datestr, file=sys.stderr)
        return None
    else:
        datelist = []
        for num in numlist:
            datelist.append(int(num))
        return datetime.datetime(datelist[2], datelist[1], datelist[0])

def execute(storage, srclist, agghosts, fromdate, todate, max_wait, all_dls):
    if fromdate == None and todate != None:
        fromdate = todate
    elif fromdate != None and todate == None:
        todate = datetime.datetime.today()

    srcobjs = datasrcs.get_srcobjs(srclist,  storage)

    download.parallel_download(srcobjs, agghosts, fromdate, todate, max_wait, all_dls)


if __name__ == '__main__':
    #initial values

    fromdate = None
    todate   = None
    srclist  = []

    debuglevel = 'info'
    progname = sys.argv[0]
    filename = None
    updateMeta = False
    updateRaw  = False
    datadir    = None
    dbname     = None
    all_dls    = False
    max_wait   = None
    agghosts   = True

    optlist, remlist = getopt.getopt(sys.argv[1:], 'ad:D:l:mnf:p:t:T:hrs:W:')
    for o, v in optlist:
        if o == '-a':
            all_dls = True
        elif o == '-d':   
            num_days = int(v)
            todate = datetime.datetime.today()
            fromdate = todate - datetime.timedelta(days = num_days)
        elif o == '-D':
            datadir = v
        elif o == '-l':
            debuglevel = v
        elif o == '-f':
            filename = v
        elif o == '-m':
            updateMeta = True
        elif o == '-n':
            agghosts = False
        elif o == '-t':
            fromdate =  to_datetime(v)
        elif o == '-T':
            todate   = to_datetime(v)
        elif o == '-r':
            updateRaw = True
        elif o == '-s':
            srclist.append(v)
        elif o == '-W':
            max_wait = int(v)
        else:
            print('Unknown option %s' % o, file=sys.stderr)
            print_usage(progname)
            sys.exit(0)

    leveldict = {'critical': logging.CRITICAL, 'error': logging.ERROR, \
                 'warning': logging.WARNING, 'info': logging.INFO, \
                 'debug': logging.DEBUG}

    logfmt  = '%(asctime)s: %(name)s: %(levelname)s %(message)s'
    datefmt = '%Y-%m-%d %H:%M:%S'

    if datadir == None:
        print('No data directory specified', file=sys.stderr)
        print_usage(progname)
        sys.exit(0)

    statsdir = os.path.join(datadir, 'stats')
    utils.mk_dir(statsdir)

    if filename:
        filename = os.path.join(statsdir, filename)

    if filename:
        logging.basicConfig(\
            level   = leveldict[debuglevel], \
            format  = logfmt, \
            filename = filename, \
            datefmt = datefmt \
        )
    else:
        logging.basicConfig(\
            level   = leveldict[debuglevel], \
            format  = logfmt, \
            datefmt = datefmt \
        )


    storage = FileManager(datadir, updateMeta, updateRaw)
    execute(storage, srclist, agghosts, fromdate, todate, max_wait, all_dls)

