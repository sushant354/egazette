import os 
import sys
import getopt
import logging

def mk_dir(dirname):
    if not os.path.exists(dirname):
        os.mkdir(dirname)

def setup_logging(loglevel, logfile, datadir=None):
    leveldict = {'critical': logging.CRITICAL, 'error': logging.ERROR, \
                 'warning': logging.WARNING,   'info': logging.INFO, \
                 'debug': logging.DEBUG}

    if loglevel not in leveldict:
        return False
    
    statsdir = None
    if datadir is not None:
        statsdir = os.path.join(datadir, 'stats')
        mk_dir(statsdir)

    logfmt  = '%(asctime)s: %(name)s: %(levelname)s %(message)s'
    datefmt = '%Y-%m-%d %H:%M:%S'
    if logfile:
        if statsdir is not None:
            logfile = os.path.join(statsdir, logfile)

        logging.basicConfig(\
            level   = leveldict[loglevel], \
            format  = logfmt, \
            filename = logfile, \
            datefmt = datefmt \
        )
    else:
        logging.basicConfig(\
            level   = leveldict[loglevel], \
            format  = logfmt, \
            datefmt = datefmt \
        )
    return True


# multiprocessing module on macs does forking weirdly, so logging doesn't work as expected
# if on darwin call this function inside the task to reinitialize logging
def setup_logging_if_needed():
    platform = sys.platform
    if platform != 'darwin':
        return
    optlist, remlist = getopt.getopt(sys.argv[1:], 'ad:D:l:mnf:p:t:T:hrs:W:')
    datadir    = None
    debuglevel = 'info'
    filename = None
    for o, v in optlist:
        if o == '-D':
            datadir = v
        elif o == '-l':
            debuglevel = v
        elif o == '-f':
            filename = v

    setup_logging(debuglevel, filename, datadir=datadir)


