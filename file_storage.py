import os
from xml.sax import saxutils
import types
import codecs
import datetime
import logging
import glob

import utils
def mk_dir(dirname):
    if not os.path.exists(dirname):
        os.mkdir(dirname)

def print_tag_file(filepath, feature):
    filehandle = codecs.open(filepath, 'w', 'utf8')

    filehandle.write(u'<?xml version="1.0" encoding="utf-8"?>\n')
    filehandle.write(obj_to_xml('document', feature))

    filehandle.close()

def obj_to_xml(tagName, obj):
    if type(obj) in types.StringTypes:
        return get_xml_tag(tagName, obj)

    tags = ['<%s>' % tagName]
    ks = obj.keys()
    ks.sort()
    for k in ks:
        newobj = obj[k]
        if isinstance(newobj, dict):
            tags.append(obj_to_xml(k, newobj))
        elif isinstance(newobj, list):
            if k == 'bench':
                tags.append(u'<%s>'% k)
                for o in newobj:
                    tags.append(obj_to_xml('name', o))
                tags.append(u'</%s>'% k)
            else:
                for o in newobj:
                    tags.append(obj_to_xml(k, o))
        elif isinstance(newobj,  datetime.datetime) or \
                isinstance(newobj, datetime.date):
            tags.append(obj_to_xml(k, date_to_xml(newobj)))
        else:
            tags.append(get_xml_tag(k, obj[k]))
    tags.append(u'</%s>' % tagName)
    xmltags =  u'\n'.join(tags)

    return xmltags

def get_xml_tag(tagName, tagValue, escape = True):
    if type(tagValue) == types.IntType:
        xmltag = u'<%s>%d</%s>' % (tagName, tagValue, tagName)
    elif type(tagValue) == types.FloatType:
        xmltag = u'<%s>%f</%s>' % (tagName, tagValue, tagName)
    else:
        if escape:
            tagValue = escape_xml(tagValue)

        xmltag = u'<%s>%s</%s>' % (tagName, tagValue, tagName)
    return xmltag

def escape_xml(tagvalue):
    return saxutils.escape(tagvalue)

def date_to_xml(dateobj):
    datedict =  {}

    datedict['day']   = dateobj.day
    datedict['month'] = dateobj.month
    datedict['year']  = dateobj.year

    return datedict

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

    def save_metainfo(self, court, relurl, metainfo):
        self.create_dirs(self.metadir, relurl)

        metapath = os.path.join(self.metadir, '%s.xml' % relurl)

        if metainfo and (self.updateMeta or not os.path.exists(metapath)):
            print_tag_file(metapath, metainfo)
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
