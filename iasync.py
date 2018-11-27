import sys
import getopt
import datetime
import logging
import re
import types
from requests.exceptions import HTTPError

from internetarchive import upload, get_session, get_item, modify_metadata
from file_storage import FileManager

import datasrcs 

class GazetteIA:
    def __init__(self, file_storage, access_key, secret_key, loglevel, logfile):
        self.file_storage = file_storage
        self.access_key   = access_key
        self.secret_key   = secret_key

        session_data = {'access': access_key, 'secret': secret_key}
        if logfile:
            logconfig    = {'logging': {'level': loglevel, 'file': logfile}}
        else:    
            logconfig    = {'logging': {'level': loglevel}}

        self.session = get_session({'s3': session_data, 'logging': logconfig})
        self.logger = logging.getLogger('iasync')
   
    def get_identifier(self, relurl, metainfo):
        srcname = self.get_srcname(relurl)
        identifier = None

        dateobj = metainfo.get_date()

        prefix    = 'in.gazette.' 
        if srcname == 'central_extraordinary':
            identifier = relurl.replace('/', '.')
            identifier = re.sub('^central_extraordinary', 'central.e', identifier)
        elif srcname == 'central_weekly':
            identifier = relurl.replace('/', '.')
            identifier = re.sub('^central_weekly', 'central.w', relurl)
        elif srcname == 'bihar':
            num = relurl.split('/')[-1]
            identifier = 'bih.gazette.%d.%s' % (dateobj.year, num)
            prefix    = 'in.gov.' 
        elif srcname == 'delhi_weekly':    
            identifier = relurl.replace('/', '.')
            identifier = re.sub('^delhi_weekly', 'delhi.w', identifier)
        elif srcname == 'delhi_extraordinary':    
            identifier = relurl.replace('/', '.')
            identifier = re.sub('^delhi_extraordinary', 'delhi.e', identifier)
        elif srcname == 'cgweekly':    
            identifier = relurl.replace('/', '.')
            identifier = re.sub('^cgweekly', 'chhattisgarh.weekly', identifier)
        elif srcname == 'cgextraordinary':    
            identifier = relurl.replace('/', '.')
            identifier = re.sub('^cgextraordinary', 'chhattisgarh.eo', identifier)
        elif srcname == 'andhra' or srcname == 'andhraarchive':    
            identifier = relurl.replace('/', '.')
        elif srcname == 'maharashtra':
            identifier = relurl.replace('/', '.')
        elif srcname == 'telangana':
            identifier = relurl.replace('/', '.')
        elif srcname == 'tamilnadu':
            relurl     = relurl.decode('ascii', 'ignore')
            relurl, n  = re.subn('[()]', '', relurl)
            identifier = relurl.replace('/', '.')
        elif srcname == 'odisha':
            identifier = relurl.replace('/', '.')
        elif srcname == 'jharkhand':
            identifier = relurl.replace('/', '.')
        elif srcname == 'madhyapradesh':
            datestr = '%s' % metainfo['date']
            gznum   = metainfo['gznum']
            gztype  = metainfo['gztype']
            identifier = 'madhya.%s.%s.%s'% (datestr, gznum, gztype)
        elif srcname == 'punjab':
            identifier = relurl.replace('/', '.')
        elif srcname == 'uttarakhand':
            relurl     = relurl.decode('ascii', 'ignore')
            relurl, n  = re.subn('[()]', '', relurl)
            identifier = relurl.replace('/', '.')
        elif srcname == 'haryana':
            identifier = relurl.replace('/', '.')
        elif srcname == 'haryanaarchive':
            identifier = relurl.replace('/', '.')
            identifier = re.sub('^haryanaarchive', 'haryanaarch', identifier)
        elif srcname == 'kerala':
            identifier = relurl.replace('/', '.')
        elif srcname == 'karnataka':    
            identifier = relurl.replace('/', '.')
            if 'links' in metainfo and metainfo['links']:
                linkids = []
                for link in metainfo['links']:
                    linkids.append(prefix + link.replace('/', '.'))
                metainfo['linkids'] = linkids
         
        identifier = prefix + identifier 
        return identifier    

    def upload(self, relurl):
        metainfo = self.file_storage.get_metainfo(relurl)
        if metainfo == None:
            self.logger.warn('No metainfo, Ignoring upload for %s' % relurl) 
            return

        identifier = self.get_identifier(relurl, metainfo)
        if identifier == None:
            self.logger.warn('Could not form IA identifier. Ignoring upload for %s' % relurl) 
            return

        item = get_item(identifier, archive_session = self.session)
        if item.exists:
            self.logger.warn('Item already exists, Ignoring upload for %s' % \
                             identifier)
            return
        else:
            print 'NOT FOUND', identifier    

        metadata = self.to_ia_metadata(relurl, metainfo)

        rawfile  = self.file_storage.get_rawfile_path(relurl)
        metafile = self.file_storage.get_metafile_path(relurl)
        try: 
            r = upload(identifier, [rawfile, metafile], metadata = metadata, \
                       access_key = self.access_key, \
                       secret_key = self.secret_key, \
                       retries=100) 
        except HTTPError as e:
           self.logger.warn('Error in upload for %s: %s', identifier, e)
        return r
  
    def get_title(self, src, metainfo):
        category = datasrcs.categories[src]
        title = [category]

        if 'date' in metainfo:
            title.append(u'%s' % metainfo['date'])

        if 'gztype' in metainfo:
            title.append(metainfo['gztype'])

        if 'partnum' in metainfo:
            partnum = metainfo['partnum']
            if re.search(r'\bPart\b', partnum):
                title.append(partnum)
            else:    
                title.append(u'Part %s' %partnum)

        if 'gznum' in metainfo:
            title.append(u'Number %s' % metainfo['gznum'])

        return u', '.join(title)

    def get_srcname(self, relurl):
       words    = relurl.split('/')
       return words[0]

    def to_ia_metadata(self, relurl, metainfo):
       src      = self.get_srcname(relurl) 

       creator   = datasrcs.srcnames[src]
       category  = datasrcs.categories[src]
       languages = datasrcs.languages[src]

       title   = self.get_title(src, metainfo)

       metadata = { \
           'collection' : 'gazetteofindia', 'mediatype' :'texts', \
           'language'   : languages, 'title': title, 'creator': creator, \
           'subject'    : category
       } 
       dateobj = metainfo.get_date()
       if dateobj:
           metadata['date'] = '%s' % dateobj
       
       metadata['description'] = self.get_description(metainfo)
       return metadata

    def get_description(self, metainfo):       
       desc = []

       ignore_keys  = set(['linknames', 'links', 'linkids'])
       keys = [ \
         ('gztype',           'Gazette Type'),  \
         ('gznum',            'Gazette Number'), \
         ('date',             'Date'), \
         ('ministry',         'Ministry'),   \
         ('department',       'Department'), \
         ('subject',          'Subject'),      \
         ('office',           'Office'), \
         ('notification_num', 'Notification Number'), \
         ('partnum',          'Part Number'), \
         ('refnum',           'Reference Number'), \
         ('linknames',        'Gazette Links'), \
         ('url',              'Gazette Source'), \
       ]
       for k, kdesc in keys:
           if k in metainfo:
               v = metainfo[k]
               if k == 'date':
                   v = '%s' % v
               elif k == 'linknames':
                  linkids = metainfo['linkids']
                  i = 0
                  v = []
                  for linkname in metainfo[k]:
                      identifier = linkids[i]
                      v.append('<a href="/details/%s">%s</a>' % \
                              (identifier, linkname))
                      i += 1
                  v = '<br/>'.join(v)
               elif k == 'url':
                  v = '<a href="%s" target="_blank">URL</a>' % v
               else:    
                   v = metainfo[k].strip()
                   
               if v:
                   desc.append((kdesc, v))

       known_keys = set([k for k, kdesc in keys])

       for k, v in metainfo.iteritems():
           if k not in known_keys and k not in ignore_keys:
               if type(v) in types.StringTypes:
                   v = v.strip()
               elif isinstance(v, list):
                   v = '%s' % v    
               if v:
                   desc.append((k.title(), v))


       desc_html = '<br/>'.join(['%s: %s' % (d[0], d[1]) for d in desc])
       return '<p>' + desc_html + '</p>'

    def update_meta(self, relurl):
        metainfo = self.file_storage.get_metainfo(relurl)
        if metainfo == None:
            self.logger.warn('No metainfo, Ignoring upload for %s' % \
                             identifier)
            return False

        identifier = self.get_identifier(relurl, metainfo)
        item = get_item(identifier, archive_session = self.session)

        if not item.exists:
            return self.upload(relurl)
        else:

            metadata = self.to_ia_metadata(relurl, metainfo)
 
            modify_metadata(identifier, metadata = metadata, \
                            access_key = self.access_key, \
                            secret_key = self.secret_key)

def print_usage(progname):
    print 'Usage: python %s [-l loglevel(critical, error, warn, info, debug)]' % progname + '''
                        [-a access_key] [-k secret_key]
                        [-f logfile]
                        [-m (update_meta)]
                        [-u (upload_to_ia)]
                        [-r relurl]
                        [-i (relurls_from_stdin)]
                        [-D gazette_directory]
                        [-t start_time (%Y-%m-%d %H:%M:%S)]
                        [-T end_time (%Y-%m-%d %H:%M:%S)]
                        [-s central_weekly -s central_extraordinary 
                         -s andhra -s andhraarchive
                         -s bihar  -s cgweekly -s cgextraordinary
                         -s delhi_weekly -s delhi_extraordinary -s karnataka
                         -s maharashtra -s telangana   -s tamilnadu
                         -s jharkhand   -s odisha      -s madhyapradesh
                         -s punjab      -s uttarakhand -s himachal
                         -s haryana     -s kerala      -s haryanaarchive
                         -s stgeorge    -s himachal    -s keralalibrary
                        ] 
    '''                     

def handle_relurl(gazette_ia, relurl, to_upload, to_update):
    if to_upload:
        gazette_ia.upload(relurl)
    elif to_update:
        gazette_ia.update_meta(relurl)    

if __name__ == '__main__':
    progname  = sys.argv[0]
    loglevel  = 'info'
    filename  = None
    datadir   = None
    start_ts  = None
    end_ts    = None
    srcnames  = []
    to_update = False
    to_upload = False
    access_key = None
    secret_key = None
    relurls    = []
    from_stdin = False

    optlist, remlist = getopt.getopt(sys.argv[1:], 'a:k:D:f:hl:s:t:T:mr:u')
    for o, v in optlist:
        if o == '-l':
            loglevel = v
        elif o == '-f':
            filename = v
        elif o == '-D':
            datadir = v
        elif o == '-t':
            start_ts = datetime.datetime.strptime(v, '%Y-%m-%d %H:%M:%S')
        elif o == '-T':
            end_ts = datetime.datetime.strptime(v, '%Y-%m-%d %H:%M:%S')
        elif o == '-s':
            srcnames.append(v)    
        elif o == '-m':
            to_update = True    
        elif o == '-u':
            to_upload = True    
        elif o == '-a':
            access_key = v    
        elif o == '-k':
            secret_key = v    
        elif o == '-r':
            relurls.append(v)    
        elif o == '-i':
            from_stdin = True    
        elif o == '-h':
            print_usage(progname)
            sys.exit(0)
        else:
            print_usage(progname)
            sys.exit(0)


    leveldict = {'critical': logging.CRITICAL, 'error': logging.ERROR, \
                 'warning': logging.WARNING,   'info': logging.INFO, \
                 'debug': logging.DEBUG}

    if loglevel not in leveldict:
        print 'Unknown log level %s' % loglevel             
        print_usage(progname)
        sys.exit(0)

    if not datadir:
        print 'Directory not specified'
        print_usage(progname)
        sys.exit(0)

    if not to_update and not to_upload:
        print 'Please specify whether to upload or update to internetarchive'
        print_usage(progname)
        sys.exit(0)

    if not access_key or not secret_key:
        print 'Please specify access and secret keys to internetarchive'
        print_usage(progname)
        sys.exit(0)

    logfmt  = '%(asctime)s: %(name)s: %(levelname)s %(message)s'
    datefmt = '%Y-%m-%d %H:%M:%S'

    if filename:
        logging.basicConfig(\
            level   = leveldict[loglevel], \
            format  = logfmt, \
            filename = filename, \
            datefmt = datefmt \
        )
    else:
        logging.basicConfig(\
            level   = leveldict[loglevel], \
            format  = logfmt, \
            datefmt = datefmt \
        )


    storage = FileManager(datadir, False, False)
    gazette_ia = GazetteIA(storage, access_key, secret_key, loglevel, filename)

    if relurls:
        for relurl in relurls:
            handle_relurl(gazette_ia, relurl, to_upload, to_update)
    elif from_stdin:
        for line in sys.stdin:
            relurl = line.strip()
            handle_relurl(gazette_ia, relurl, to_upload, to_update)
    else:        
        for relurl in storage.find_matching_relurls(srcnames, start_ts, end_ts):
            handle_relurl(gazette_ia, relurl, to_upload, to_update)


    
