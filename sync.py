import datetime
import sys
import os
import logging
import re
import click
import utils
import datasrcs
import download
from file_storage import FileManager

def print_usage(progname):
    print '''Usage: %s [-l loglevel(critical, error, warn, info, debug)]
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
                       ''' % progname

    print 'The program will download gazettes from various egazette sites'
    print 'and will place in a specified directory. Gazettes will be'
    print 'placed into directories named by type and date. If fromdate or'
    print 'todate is not specified then the default is your current date.'

def to_datetime(datestr):
    numlist = re.findall('\d+', datestr)
    if len(numlist) != 3:
        print >>sys.stderr, '%s not in correct format [DD/MM/YYYY]' % datestr
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

@click.command()
@click.option('-a', help='')
@click.option('-d', help='')
@click.option('-D', help='')
@click.option('-l', help='')
@click.option('-f', help='')
@click.option('-m', help='')
@click.option('-n', help='')
@click.option('-t', help='')
@click.option('-T', help='')
@click.option('-r', help='')
@click.option('-s', help='')
@click.option('-W', help='')
def main(a, d, D, l, f, m, n, t, T, r, s, W):
    srclist = []
    progname = sys.argv[0]
    all_dls = True
    num_days = int(d)
    todate = datetime.datetime.today()
    fromdate = todate - datetime.timedelta(days=num_days)
    datadir = D
    debuglevel = l
    filename = f
    updateMeta = True
    agghosts = False
    fromdate = to_datetime(t)
    todate = to_datetime(T)
    updateRaw = True
    srclist.append(s)
    max_wait = int(W)

    leveldict = {'critical': logging.CRITICAL, 'error': logging.ERROR, \
                 'warning': logging.WARNING, 'info': logging.INFO, \
                 'debug': logging.DEBUG}

    logfmt = '%(asctime)s: %(name)s: %(levelname)s %(message)s'
    datefmt = '%Y-%m-%d %H:%M:%S'

    if datadir == None:
        print >> sys.stderr, 'No data directory specified'
        print_usage(progname)
        sys.exit(0)

    statsdir = os.path.join(datadir, 'stats')
    utils.mk_dir(statsdir)

    if filename:
        filename = os.path.join(statsdir, filename)

    if filename:
        logging.basicConfig( \
            level=leveldict[debuglevel], \
            format=logfmt, \
            filename=filename, \
            datefmt=datefmt \
            )
    else:
        logging.basicConfig( \
            level=leveldict[debuglevel], \
            format=logfmt, \
            datefmt=datefmt \
            )

    storage = FileManager(datadir, updateMeta, updateRaw)
    execute(storage, srclist, agghosts, fromdate, todate, max_wait, all_dls)


if __name__ == '__main__':
    #initial values
    main()
