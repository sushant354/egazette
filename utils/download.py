import multiprocessing
import urllib.request, urllib.error, urllib.parse
import time
import logging
import re

from . import proxylist

def sync(hostname, gazetteobjs, fromdate, todate, event):
    if hostname in proxylist.hostdict:
        proxy = urllib.request.ProxyHandler(proxylist.hostdict[hostname])
        opener = urllib.request.build_opener(proxy)
        urllib.request.install_opener(opener)

    for obj in gazetteobjs:
        if fromdate == None and todate == None:
            obj.sync_daily(event)
        else:    
            obj.sync(fromdate, todate, event)

def all_downloads(hostname, gazetteobjs, event):
    for obj in gazetteobjs:
        obj.all_downloads(event)

def agg_host_processes(gazetteobjs, all_dls, fromdate, todate, event):
    srcdict = {}
    for src in gazetteobjs:
        hostname = src.hostname
        if not (hostname in srcdict):
            srcdict[hostname] = []
        srcdict[hostname].append(src)

    tlist = []
    for hostname, srclist in srcdict.items():
        if all_dls:
            t = multiprocessing.Process(target = all_downloads, args = (hostname, srclist, event))
        else:
            t = multiprocessing.Process(target = sync, args = \
                                (hostname, srclist, fromdate, todate, event))
        t.start()
        tlist.append(t)

    return tlist

def noagg_host_processes(gazetteobjs, all_dls, fromdate, todate, event):
    tlist = []
    for src in gazetteobjs:
        if all_dls:
            t = multiprocessing.Process(target = all_downloads, args = (src.hostname, [src], event))
        else:
            t = multiprocessing.Process(target = sync, args = \
                                (src.hostname, [src], fromdate, todate, event))
        t.start()
        tlist.append(t)

    return tlist

def parallel_download(gazetteobjs, agghosts, fromdate, todate, max_wait, all_dls):
    event = multiprocessing.Event()
    if agghosts:
        tlist = agg_host_processes(gazetteobjs, all_dls, fromdate, todate, event)
    else:
        tlist = noagg_host_processes(gazetteobjs, all_dls, fromdate, todate, event)

    start_ts = time.time()
    for t in tlist:
        if max_wait != None and max_wait <= 5:
            break

        t.join(max_wait)
        end_ts    = time.time()
        if max_wait != None:
            elapsed   = end_ts - start_ts
            max_wait -= elapsed
            start_ts  = end_ts

    if max_wait:       
        logger = logging.getLogger('crawler.controller')
        logger.warning('Time expired. Setting the event and asking the crawlers to exit')
        event.set()
        for t in tlist:
            if t.is_alive():
                t.join()

  

