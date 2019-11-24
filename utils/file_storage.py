import os
import logging
import glob
import time

from . import utils
from . import xml_ops

def mk_dir(dirname):
    if not os.path.exists(dirname):
        os.mkdir(dirname)


class FileManager:
    def __init__(self, basedir, updateMeta, updateRaw):
        self.logger = logging.getLogger('judis.filemanager')

        self.rawdir = os.path.join(basedir, 'raw')
        self.metadir = os.path.join(basedir, 'metatags')

        self.updateRaw  = updateRaw
        self.updateMeta = updateMeta

        mk_dir(self.rawdir)
        mk_dir(self.metadir)

    def create_dirs(self, dirname, relurl):
        words = relurl.split('/')
        for word in words[:-1]: 
            dirname = os.path.join(dirname, word)
            mk_dir(dirname)

    def get_metainfo(self, relurl):
        metapath = os.path.join(self.metadir, '%s.xml' % relurl)
        if os.path.exists(metapath):
            return xml_ops.read_tag_file(metapath, relurl)

        return None   
         
    def get_rawfile_path(self, relurl):
        rawpath  = os.path.join(self.rawdir, relurl)
        rawpaths = glob.glob('%s.*' % rawpath)
        if rawpaths:
            return rawpaths[0]

        return None    

    def get_metafile_path(self, relurl):
        metapath = os.path.join(self.metadir, '%s.xml' % relurl)
        if os.path.exists(metapath):
            return metapath
        return None    

    def save_metainfo(self, court, relurl, metainfo):
        self.create_dirs(self.metadir, relurl)

        metapath = os.path.join(self.metadir, '%s.xml' % relurl)

        if metainfo and (self.updateMeta or not os.path.exists(metapath)):
            xml_ops.print_tag_file(metapath, metainfo)
            return True
        return False 

    def download_stats(self, start_time, end_time):
        return None, None
        
    def save_binary_file(self, filepath, buf):
        h = open(filepath, 'wb')
        h.write(buf)
        h.close()

    def should_download_raw(self, relurl, judge_url, validurl = True):
        rawpath  = os.path.join(self.rawdir, relurl)
        return self.updateRaw or not glob.glob('%s.*' % rawpath)

    def get_file_extension(self, doc):
        mtype = utils.get_buffer_type(doc)
        return utils.get_file_extension(mtype)

    def save_rawdoc(self, court, relurl, encoding, doc):
        self.create_dirs(self.rawdir, relurl)
        rawpath  = os.path.join(self.rawdir, relurl)

        if doc and (self.updateRaw or not glob.glob('%s.*' % rawpath)):
            extension = self.get_file_extension(doc)
            self.save_binary_file('%s.%s' % (rawpath, extension), doc)
            return True
        return False
        

    def recursive_relurls(self, datadir, relurl):
        current_dir = os.path.join(datadir, relurl)
        if os.path.isfile(current_dir):
            tmprel = relurl.rsplit('.', 1)[0]
            yield tmprel

        if os.path.isdir(current_dir):
            filenames = os.listdir(current_dir)
            filenames.sort()
            for filename in filenames:
                tmprel = os.path.join(relurl, filename)
                for rel1 in self.recursive_relurls(datadir, tmprel):
                    yield rel1
                
                    
    def find_matching_relurls(self, srcs, start_ts, end_ts):         
        srcs = set(srcs)

        if start_ts:
            start_ts = time.mktime(start_ts.timetuple())

        if end_ts:
            end_ts = time.mktime(end_ts.timetuple())

        srclist = os.listdir(self.rawdir)
        srclist.sort()
        for src in srclist:
            if srcs and src not in srcs:
                continue
      
            for relurl in self.recursive_relurls(self.rawdir, src):
                rawpath   = self.get_rawfile_path(relurl)
                metapath  = self.get_metafile_path(relurl)

                if not os.path.isfile(rawpath):
                    continue

                if not metapath or not os.path.isfile(metapath):
                    continue

                if start_ts != None and os.path.getmtime(rawpath) < start_ts \
                        and  os.path.getmtime(metapath) < start_ts:
                    continue 

                if end_ts != None and os.path.getmtime(rawpath) > end_ts \
                        and  os.path.getmtime(metapath) > end_ts:
                    continue 
                yield relurl    
