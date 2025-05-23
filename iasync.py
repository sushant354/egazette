import sys
import getopt
import datetime
import logging
import re
import shutil
import os
import time
from requests.exceptions import HTTPError
from zipfile import ZipFile
import codecs

from internetarchive import upload, get_session, get_item, modify_metadata
from egazette.utils.file_storage import FileManager

from egazette.utils import reporting
from egazette.srcs  import datasrcs 
from egazette.utils import utils
from egazette.utils import pdf_ops
from egazette.gvision import get_google_client, to_hocr, pdf_to_jpg, compress_file, LangTags

class Stats:
    def __init__(self):
        self.uploads = {}
        self.upload_success = {}

        self.modify = {}
        self.modify_success = {}

    def update_upload(self, srcname, success):    
        self.update(srcname, success, self.uploads, self.upload_success)

    def update_modify(self, srcname, success):    
        self.update(srcname, success, self.modify, self.modify_success)

    def update(self, srcname, success, total, total_success):
        if srcname not in total:
            total[srcname]         = 0
            total_success[srcname] = 0

        total[srcname] += 1

        if success:
            total_success[srcname] += 1

    def get_msg_by_srcs(self, msg, total, total_success):
        msg.append('------------')
        msg.append('Srcname\tTotal\tSuccess')
        keys = list(total.keys())
        keys.sort()
        for srcname in keys:
            msg.append('%s\t%d\t%d' % (srcname, total[srcname], total_success[srcname]))
        msg.append('\n')                                   

    def get_message(self, srcnames):
        msg = []
        if self.uploads:
            msg.append('Upload Stats')
            self.get_msg_by_srcs(msg, self.uploads, self.upload_success)

        if self.modify:    
            msg.append('Modify Stats')
            self.get_msg_by_srcs(msg, self.modify, self.modify_success)
        
        noupdate = []
        for src in srcnames:
            if src not in self.uploads and src not in self.modify:
                noupdate.append(src)
        if noupdate:
             msg.append('No updates from %s' % ', '.join(noupdate))
        return '\n'.join(msg)

def create_zip(zipfile, filenames):
    zipobj = ZipFile(zipfile, 'w')
    for filename in filenames:
        head, tail   = os.path.split(filename)
        head1, tail1 = os.path.split(head)
        dirpath = os.path.join(tail1, tail)
        zipobj.write(filename, dirpath)
    zipobj.close()

def atoi(text):
    return int(text) if text.isdigit() else text

def natural_keys(text):
    return [ atoi(c) for c in re.split('(\d+)', text) ]

class Gvision:
    def __init__(self, iadir, key_file):
        self.client = get_google_client(key_file)
        self.iadir  = iadir

    def mkdir(self, path):
        if not os.path.exists(path):
            os.mkdir(path)

    def convert_to_jpg_hocr(self, identifier, filepath):
        path, filename  = os.path.split(filepath)
        name, n = re.subn('.pdf$', '', filename)

        item_path = os.path.join(self.iadir, identifier)
        jpgdir    = os.path.join(item_path, name + '_jpg')
        gocrdir   = os.path.join(item_path, name + '_gocr')
        hocrfile  = os.path.join(item_path, name + '_chocr.html')

        self.mkdir(item_path)
        self.mkdir(jpgdir)
        self.mkdir(gocrdir)

        success = pdf_to_jpg(filepath, jpgdir, 300)
        if not success:
            self.logger.warning('Could not convert into jpg files %s', filepath)
            return None, None

        filenames = os.listdir(jpgdir)
        filenames.sort(key=natural_keys)

        outhandle = codecs.open(hocrfile, 'w', encoding = 'utf8')
        langtags  = LangTags()
        to_hocr(jpgdir, filenames, self.client, outhandle, gocrdir, 300, langtags)
        outhandle.close()
        
        hocrfile_gz =  hocrfile + '.gz'
        compress_file(hocrfile, hocrfile_gz)

        jpgzip   = jpgdir + '.zip'
        jpgfiles = [os.path.join(jpgdir, x) for x in filenames]

        create_zip(jpgzip, jpgfiles)
        if os.path.exists(jpgdir):
            shutil.rmtree(jpgdir)

        return jpgzip, hocrfile_gz

class GazetteIA:
    def __init__(self, gvisionobj, file_storage, access_key, secret_key, \
                 loglevel, logfile):
        self.gvisionobj   = gvisionobj         
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

        self.num_upload_retries = 100
        self.num_reattempts = 5
        self.reattempt_delay_secs = 300
   
    def get_identifier(self, relurl, metainfo):
        srcname    = self.get_srcname(relurl)
        #relurl     = relurl.decode('ascii', 'ignore')
        identifier = None

        dateobj = metainfo.get_date()

        prefix    = 'in.gazette.' 
        if srcname == 'central_extraordinary':
            identifier = relurl.replace('/', '.')
            identifier = re.sub('^central_extraordinary', 'central.e', identifier)
        elif srcname == 'central_weekly':
            identifier = relurl.replace('/', '.')
            identifier = re.sub('^central_weekly', 'central.w', identifier)
        elif srcname == 'bihar':
            num = relurl.split('/')[-1]
            identifier = 'bih.gazette.%s.%s' % (dateobj, num)
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
        elif srcname == 'punjabdsa':
            identifier = relurl.replace('/', '.')
        elif srcname == 'uttarakhand':
            relurl, n  = re.subn('[()]', '', relurl)
            identifier = relurl.replace('/', '.')
        elif srcname == 'haryana':
            relurl, n  = re.subn("[',&:%\s;()–]", '', relurl)
            identifier = relurl.replace('/', '.')
        elif srcname == 'haryanaarchive':
            identifier = relurl.replace('/', '.')
            identifier = re.sub('^haryanaarchive', 'haryanaarch', identifier)
        elif srcname == 'kerala':
            relurl, n  = re.subn("[',&:%\s;()]", '', relurl)
            identifier = relurl.replace('/', '.')
            identifier = re.sub('^kerala', 'kerala_new', identifier)
            identifier = identifier[:80]
        elif srcname == 'karnataka':    
            identifier = self.get_karnataka_identifier(relurl)
            if 'links' in metainfo and metainfo['links']:
                linkids = []
                for link in metainfo['links']:
                    linkids.append(prefix+self.get_karnataka_identifier(link))

                metainfo['linkids'] = linkids
        elif srcname == 'goa':    
            prefix = 'in.goa.egaz.' 
            gznum  = metainfo['gznum']
            series = metainfo['series']
            identifier = '%s.%s' % (gznum, series)
        else:
            identifier = relurl.replace('/', '.')
         
        identifier = prefix + identifier 
        return identifier    

    def get_karnataka_identifier(self, relurl):
        identifier = relurl.replace('/', '.')
        identifier = re.sub('^karnataka', 'karnataka_new', identifier)
        return identifier

    def get_ia_item(self, identifier):
        try:
            item = get_item(identifier, archive_session = self.session)
        except Exception as e:
            self.logger.warning('Could not get item %s. Error %s' , identifier, e) 
            item = None 
        return item

    def ocr_files(self, identifier, to_upload):
        final = []
        for filepath in to_upload:
            if re.search('pdf$', filepath):
                jpgzip, hocrzip = self.gvisionobj.convert_to_jpg_hocr(identifier, filepath)
                if jpgzip:
                    final.append(jpgzip)
                if hocrzip:
                    final.append(hocrzip)
            else:
                final.append(filepath)

        return final

    def upload(self, relurl):
        metainfo = self.file_storage.get_metainfo(relurl)
        if metainfo == None:
            self.logger.warning('No metainfo, Ignoring upload for %s' % relurl) 
            return False

        identifier = self.get_identifier(relurl, metainfo)
        if identifier == None:
            self.logger.warning('Could not form IA identifier. Ignoring upload for %s' % relurl) 
            return False

        while 1:
            item = self.get_ia_item(identifier)
            if item:
                break
            time.sleep(self.reattempt_delay_secs)

        rawfile  = self.file_storage.get_rawfile_path(relurl)
        metafile = self.file_storage.get_metafile_path(relurl)

        if item.exists:    
            filelist = item.get_files() 

            files = set([f.name for f in filelist])
            rawname  = rawfile.split('/')[-1]
            metaname = metafile.split('/')[-1]

            to_upload = []
            if rawname in files:
                self.logger.info('Rawfile already exists for %s. Ignoring.' % \
                                 relurl)
            else:
                to_upload.append(rawfile)

            if metaname in files:
                self.logger.info('Metafile already exists for %s. Ignoring.' % \
                                 relurl)
            else:
                to_upload.append(metafile)
            metadata = None    
        else: 
            files = set([]) 
            metadata  = self.to_ia_metadata(relurl, metainfo)
            to_upload = [rawfile, metafile]

        if not to_upload:
            self.logger.info('No files need to be uploaded for %s', identifier)
            return False

        if self.gvisionobj:
            to_upload = self.ocr_files(identifier, to_upload)
            if metadata == None:
                metadata = {}
            metadata['ocr'] = 'google-cloud-vision IndianKanoon 1.0'
            metadata['fts-ignore-ingestion-lang-filter'] = 'true'

        success = self.ia_upload(identifier, metadata, to_upload, files)

        if success:
            self.logger.info('Successfully uploaded %s', identifier)
        else:
            self.logger.warning('Error in uploading %s', identifier)

        if self.gvisionobj and to_upload:
            for filepath in to_upload:
                os.remove(filepath)

        return success

    def pop_rawfile(self, to_upload):
        idx = -1
        for i,file in enumerate(to_upload):
            if file.endswith('.pdf'):
                idx = i
                break

        if idx == -1:
            return None
        
        return to_upload.pop(idx)

    def ia_upload(self, identifier, metadata, to_upload, files):
        uploaded = False
        bad_pdf_detected = False
        to_del = []

        count = self.num_reattempts
        while count > 0:
            try:
                if metadata:
                    upload(identifier, to_upload, metadata = metadata, \
                           access_key = self.access_key, \
                           secret_key = self.secret_key, \
                           retries=self.num_upload_retries)
                else:               
                    upload(identifier, to_upload, \
                           access_key = self.access_key, \
                           secret_key = self.secret_key, \
                           retries=self.num_upload_retries)
                uploaded = True
                break
            except HTTPError as e:
                self.logger.warning('Error in upload for %s: %s', identifier, e)

                msg = str(e)
                if re.search('Syntax error detected in pdf data', msg) or \
                       re.search('error checking pdf file', msg):
                    if bad_pdf_detected:
                        self.logger.warning('Already attempted fixing bad pdf, giving up for %s: %s', \
                                            identifier, e)
                        break
                    bad_pdf_detected = True

                    rawfile = self.pop_rawfile(to_upload)

                    if rawfile is None:
                        self.logger.error('Unable to locate the bad pdf for %s', identifier)
                        break

                    renamed_pdf_file = self.rename_bad_pdf(rawfile)
                    to_del.append(renamed_pdf_file)
                    if renamed_pdf_file in files:
                        self.logger.warning('Renamed PDF file already exists. Ignoring. for %s', identifier)
                    else:
                        to_upload.append(renamed_pdf_file)

                    corrected_pdf_file = self.create_corrected_pdf(rawfile)
                    if corrected_pdf_file is not None:
                        to_upload.append(corrected_pdf_file)
                        to_del.append(corrected_pdf_file)
                    continue

                elif re.search('pdf requires a password', msg):

                    rawfile = self.pop_rawfile(to_upload)

                    if rawfile is None:
                        self.logger.error('Unable to locate the bad locked pdf for %s', identifier)
                        break

                    renamed_pdf_file = self.rename_bad_pdf(rawfile)
                    to_del.append(renamed_pdf_file)
                    if renamed_pdf_file in files:
                        self.logger.warning('Renamed PDF file already exists. Ignoring. for %s', identifier)
                    else:
                        to_upload.append(renamed_pdf_file)
                    continue

            except Exception as e:
                self.logger.warning('Error in upload for %s: %s', identifier, e)

            count = count - 1 
            time.sleep(self.reattempt_delay_secs)

        for file in to_del:
            os.remove(file)

        return uploaded


    def rename_bad_pdf(self, rawfile):
        name = '%s-' %rawfile.split('/')[-1]
        tmpfile = '/tmp/%s' % name
        shutil.copyfile(rawfile, tmpfile)
        return tmpfile

    def create_corrected_pdf(self, rawfile):
        name = '%s' %rawfile.split('/')[-1]

        tmpfile = '/tmp/%s' % name

        try:
            pdf_ops.convert_to_image_pdf_file(rawfile, tmpfile)
            return tmpfile
        except Exception as ex:
            self.logger.error('Unable to convert unacceptble pdf file to image pdf file, ex: %s', ex)
            return None


    def get_title(self, src, metainfo):
        category = datasrcs.categories[src]
        title = [category]

        if 'date' in metainfo:
            title.append('%s' % metainfo['date'])

        if 'gztype' in metainfo:
            title.append(metainfo['gztype'])

        if 'partnum' in metainfo:
            partnum = metainfo['partnum']
            if re.search(r'\bPart\b', partnum):
                title.append(partnum)
            else:    
                title.append('Part %s' %partnum)

        if 'gznum' in metainfo:
            title.append('Number %s' % metainfo['gznum'])

        return ', '.join(title)

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
         ('num',              'Number'), \
         ('gazetteid',        'Gazette ID'), \
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
                  v = '<a href="%s">URL</a>' % v
               else:    
                   v = metainfo[k].strip()
                   
               if v:
                   desc.append((kdesc, v))

       known_keys = set([k for k, kdesc in keys])

       for k, v in metainfo.items():
           if k not in known_keys and k not in ignore_keys:
               if type(v) in (str,):
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
            self.logger.warning('No metainfo, Ignoring upload for %s' % relurl)
            return False

        identifier = self.get_identifier(relurl, metainfo)

        while 1:
            item = self.get_ia_item(identifier)
            if item:
                break
            time.sleep(self.reattempt_delay_secs)

        if not item.exists:
            return self.upload(relurl)
        else:
            metadata = self.to_ia_metadata(relurl, metainfo)
            while 1:
                if self.ia_modify_metadat(identifier, metadata):
                    break
                time.sleep(self.reattempt_delay_secs)    
 
        return True

    def ia_modify_metadat(self, identifier, metadata):
        try:
            modify_metadata(identifier, metadata = metadata, \
                            access_key = self.access_key, \
                            secret_key = self.secret_key)
        except Exception as e:
            self.logger.warning('Could not  modify metadata %s. Error %s' , identifier, e)
            return False
        return True        

def print_usage(progname):
    print('Usage: python %s [-l loglevel(critical, error, warn, info, debug)]' % progname + '''
                        [-a access_key] [-k secret_key]
                        [-f logfile]
                        [-m (update_meta)]
                        [-u (upload_to_ia)]
                        [-r relurl]
                        [-i (relurls_from_stdin)]
                        [-d days_to_sync]
                        [-D gazette_directory]
                        [-I internet_archive_directory]
                        [-g google_gvision_key]
                        [-t start_time (%Y-%m-%d %H:%M:%S)]
                        [-T end_time (%Y-%m-%d %H:%M:%S)]
                        [-p postmark_token]
                        [-E email_to_report]
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
    ''')                     

def handle_relurl(gazette_ia, relurl, to_upload, to_update, stats):
    srcname = gazette_ia.get_srcname(relurl)

    if to_upload:
        success = gazette_ia.upload(relurl)
        stats.update_upload(srcname, success)
    elif to_update:
        success = gazette_ia.update_meta(relurl)   
        stats.update_modify(srcname, success)

if __name__ == '__main__':
    progname  = sys.argv[0]
    loglevel  = 'info'
    logfile   = 'iasync-%s.txt' % datetime.date.today()
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

    server_token = None
    from_addr    = None
    to_addrs   = []
    key_file   = None
    iadir      = None

    optlist, remlist = getopt.getopt(sys.argv[1:], 'a:k:d:D:f:g:hiI:l:s:t:T:mr:uE:p:U:')
    for o, v in optlist:
        if o == '-l':
            loglevel = v
        elif o == '-f':
            logfile = v
        elif o == '-d':
            num_days = int(v)
            today    = datetime.date.today()
            lastday  = today - datetime.timedelta(days = num_days)
            start_ts = datetime.datetime(lastday.year, lastday.month, lastday.day, 5, 0, 0)
            end_ts   = datetime.datetime(today.year, today.month, today.day, 5, 0, 0)
            
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
        elif o == '-U':
            from_addr = v
        elif o == '-a':
            access_key = v    
        elif o == '-k':
            secret_key = v    
        elif o == '-r':
            relurls.append(v)    
        elif o == '-i':
            from_stdin = True    
        elif o == '-E':
            to_addrs.append(v)
        elif o == '-p':
            server_token = v
        elif o == '-I':
            iadir = v
        elif o == '-g':
            key_file = v
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
        print('Unknown log level %s' % loglevel)             
        print_usage(progname)
        sys.exit(0)

    if not datadir:
        print('Directory not specified')
        print_usage(progname)
        sys.exit(0)

    if not to_update and not to_upload:
        print('Please specify whether to upload or update to internetarchive')
        print_usage(progname)
        sys.exit(0)

    if not access_key or not secret_key:
        print('Please specify access and secret keys to internetarchive')
        print_usage(progname)
        sys.exit(0)

    if to_addrs and (not server_token or not from_addr):
        print('To report through email, please specify postmark server token/from_addr')
        print_usage(progname)
        sys.exit(0)

    if (key_file and not iadir) or (iadir and not key_file):
        print('Please specify google key file and internetarchive directory both for using OCR while uploading files')
        print_usage(progname)
        sys.exit(0)

    gvisionobj = None
    if key_file and iadir:
        gvisionobj = Gvision(iadir, key_file)
        
    logfmt  = '%(asctime)s: %(name)s: %(levelname)s %(message)s'
    datefmt = '%Y-%m-%d %H:%M:%S'

    if logfile:
        statsdir = os.path.join(datadir, 'stats')
        utils.mk_dir(statsdir)

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


    storage = FileManager(datadir, False, False)
    gazette_ia = GazetteIA(gvisionobj, storage, access_key, secret_key, loglevel, logfile)
    stats        = Stats()

    if len(srcnames) == 0:
        srcnames = datasrcs.srcdict.keys()

    if relurls:
        for relurl in relurls:
            handle_relurl(gazette_ia, relurl, to_upload, to_update, stats)
    elif from_stdin:
        for line in sys.stdin:
            relurl = line.strip()
            handle_relurl(gazette_ia, relurl, to_upload, to_update, stats)
    else:        
        for relurl in storage.find_matching_relurls(srcnames, start_ts, end_ts):
            handle_relurl(gazette_ia, relurl, to_upload, to_update, stats)



    if to_addrs:
        msg = stats.get_message(srcnames)
        reporting.report(server_token, from_addr, to_addrs,   \
                        'Stats for gazette on %s' % datetime.date.today(), msg)
