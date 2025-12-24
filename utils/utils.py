import os
import re
import types
import urllib.parse
import calendar
import magic
import datetime
import sys
import calendar
import logging

from xml.parsers.expat import ExpatError
from xml.dom import minidom, Node
from bs4 import BeautifulSoup, NavigableString, Tag

def parse_xml(xmlpage):
    try: 
        d = minidom.parseString(xmlpage)
    except ExpatError:
        d = None
    return d

def get_node_value(xmlNodes):
    value = [] 
    ignoreValues = ['\n']
    for node in xmlNodes:
        if node.nodeType == Node.TEXT_NODE:
            if node.data not in ignoreValues:
                value.append(node.data)
    return ''.join(value)

def remove_spaces(x):
    x, n = re.subn('\s+', ' ', x)
    return x.strip()

def get_selected_option(select):
    option = select.find('option', {'selected': 'selected'})
    if option == None:
        option = select.find('option')

    if option == None:
        return ''

    val = option.get('value')
    if val == None:
        val = ''

    return val

def replace_field(formdata, k, v):
    newdata = []
    for k1, v1 in formdata:
        if k1 == k:
            newdata.append((k1, v))
        else:
            newdata.append((k1, v1))
    return newdata

def remove_fields(postdata, fields):
    newdata = []
    for k, v in postdata:
        if k not in fields:
            newdata.append((k, v))
    return newdata


def find_next_page(el, pagenum):
    nextpage = None

    links = el.findAll('a')

    if len(links) <= 0:
        return None

    for link in links:
        contents = get_tag_contents(link)
        try:
            val = int(contents)
        except ValueError:
            continue

        if val == pagenum + 1 and link.get('href'):
            nextpage = {'href': link.get('href'), 'title': f'{val}'}
            break

    return nextpage


def check_next_page(tr, pagenum):
    links    = tr.findAll('a')

    if len(links) <= 0:
        return False, None

    for link in links:
        contents = get_tag_contents(link)
        if not contents:
            continue
        contents = contents.strip()
        if  not re.match('[\d.]+$', contents):
            return False, None

    pageblock = True
    nextlink  = None

    for link in links:
        contents = get_tag_contents(link)
        try:
            val = int(contents)
        except ValueError:
            continue

        if val == pagenum + 1 and link.get('href'):
            nextlink = {'href': link.get('href'), 'title': '%d' % val}
            break

    return pageblock, nextlink

def month_to_num(month):
    month = month.lower()
    if month in ['frbruary', 'februay']:
        month = 'february'

    count = 0
    for mth in calendar.month_name:
        if mth.lower() == month:
            return count
        count += 1

    count = 0
    for mth in calendar.month_abbr:
        if mth.lower() == month:
            return count
        count += 1

    return None

def to_dateobj(x):
    reobj = re.search('(?P<day>\d+)-(?P<month>jan|feb|mar|apr|may|jun|jul|aug|sep|aug|sep|oct|nov|dec)-(?P<year>\d+)', x, re.IGNORECASE)
    if reobj:
        groupdict = reobj.groupdict()
        month = month_to_num(groupdict['month'])
        day   = int(groupdict['day'])
        year  = int(groupdict['year'])
        return datetime.date(year, month, day)

    return None    

def get_month_num(month, monthnames):
    i = 0
    month = month.lower()
    for m in monthnames:
        if m.lower() == month:
            return i
        i += 1
    return -1
            
def parse_datestr(datestr):
    reobj = re.search('(?P<day>\d+)\s*(?P<month>\w+)\s*(?P<year>\d+)', datestr)
    if reobj:
        groupdict = reobj.groupdict()
        month_num = get_month_num(groupdict['month'], calendar.month_abbr)
        if month_num <= 0:
            return None
        try:
            year = int(groupdict['year'])
            day  = int(groupdict['day'])    
        except:
            return None    
        return datetime.datetime(year, month_num, day)

    return None         

def parse_webpage(webpage, parser):
    try:
        d = BeautifulSoup(webpage, parser)
        return d
    except:
        return None

def get_search_form(webpage, parser, search_endp):
    d = parse_webpage(webpage, parser)
    if d is None:
        return None

    search_form = d.find('form', {'action': search_endp})
    if search_form is None:
        return None 

    return search_form

def url_to_filename(url, catchpath, catchquery):
    htuple = urllib.parse.urlparse(url)
    path   = htuple[2]

    words = []

    if catchpath:
        pathwords = path.split('/')
        words.extend(pathwords)
    
    if catchquery:
        qs = htuple[4].split('&')
        qdict = {}
        for q in qs:
            x = q.split('=')
            if len(x) == 2:
                qdict[x[0]] = x[1]
        for q in catchquery:
            if q in qdict:
                words.append(qdict[q])

    if words:
        wordlist = []
        for word in words:
            word =  word.replace('/', '_')
            word = word.strip()
            wordlist.append(word)
            
        filename = '_'.join(wordlist)
        return filename
    return None

def get_tag_contents(node):
    if type(node) == NavigableString:
        return '%s' % node 

    retval = [] 
    for content in node.contents:
        if type(content) == NavigableString:
            retval.append(content)
        elif type(content) == Tag and content.name not in ['style', 'script']:
            if content.name not in ['span']:
                retval.append(' ')
            retval.append(get_tag_contents(content))

    return ''.join(retval) 

def get_date_from_title(title):
    months =  '|'.join(calendar.month_name[1:]) 
    reobj = re.search(r'(?P<day>\d+)\s*(st|nd|rd|th)\s*(?P<month>%s)\s*(?P<year>\d{4})\b' % months, title, re.IGNORECASE)
    if not reobj:
        return None

    groupdict = reobj.groupdict()

    day    = groupdict['day']
    month  = groupdict['month']
    year   = groupdict['year']

    month_num = get_month_num(groupdict['month'], calendar.month_name)
    if month_num <= 0:
        return None

    try:
        dateobj = datetime.date(int(year), month_num, int (day))
    except:    
        dateobj = None    
    return dateobj
        
def tag_contents_without_recurse(tag):
    contents = []
    for content in tag.contents:
        if type(content) == NavigableString:
            contents.append(content)

    return contents
 
def mk_dir(dirname):
    if not os.path.exists(dirname):
        os.mkdir(dirname)

def pad_zero(t):
    if t < 10:
        tstr = '0%d' % t
    else:
        tstr = '%d' % t

    return tstr

def get_egz_date(dateobj):
    return '%s-%s-%s' % (pad_zero(dateobj.day), calendar.month_abbr[dateobj.month], dateobj.year)

def dateobj_to_str(dateobj, sep, reverse = False):
    if reverse:
        return '%s%s%s%s%s' % (pad_zero(dateobj.year), sep, \
                pad_zero(dateobj.month), sep, pad_zero(dateobj.day))
    else:
        return '%s%s%s%s%s' % (pad_zero(dateobj.day), sep, \
                pad_zero(dateobj.month), sep, pad_zero(dateobj.year))
  

URL        = 'url'
HREF       = 'href'
TITLE      = 'title'
DATE       = 'date'
MINISTRY   = 'ministry'
SUBJECT    = 'subject'
GZTYPE     = 'gztype'
GZNUM      = 'gznum'
DEPARTMENT = 'department'
OFFICE     = 'office'
NOTIFICATION_NUM = 'notification_num'
PART_NUM   = 'partnum'
REF_NUM    = 'refnum'
LINK_NAMES = 'linknames'
NUM        = 'num'
GZ_ID      = 'gazetteid'
BUNDLE_NO  = 'bundleno'
CITY       = 'city'
DESCRIPTION = 'description'
FILE       = 'file'
TOPIC      = 'topic'
YEAR       = 'year'
PUBLISHER  = 'publisher'
SUBDEPARTMENT = 'subdepartment'
DOCTYPE    = 'doctype'
CATEGORY   = 'category'

_illegal_xml_chars_RE = re.compile('[\x00-\x08\x0b\x0c\x0e-\x1F\uD800-\uDFFF\uFFFE\uFFFF]')

def replace_xml_illegal_chars(val, replacement=' '):
    """Filter out characters that are illegal in XML."""

    return _illegal_xml_chars_RE.sub(replacement, val)

class MetaInfo(dict):
    def __init__(self):
        dict.__init__(self)

    def copy(self):
        m = MetaInfo()
        for k, v in self.items():
            m[k] = v
        return m
 
    def set_field(self, field, value):
        if type(value) in (str,):
            value = replace_xml_illegal_chars(value)
        self.__setitem__(field, value)

    def get_field(self, field):
        if field in self:
            return self.get(field)
        return None

    def set_date(self, value):
        self.set_field(DATE, value)

    def set_title(self, value):
        self.set_field(TITLE, value)

    def set_url(self, value):
        self.set_field(URL, value)

    def set_href(self, value):
        self.set_field(HREF, value)

    def set_subject(self, value):
        self.set_field(SUBJECT, value)

    def set_ministry(self, value):
        self.set_field(MINISTRY, value)

    def set_gztype(self, value):
        self.set_field(GZTYPE, value)
    
    def set_gznum(self, value):
        self.set_field(GZNUM, value)

    def set_department(self, value):
        self.set_field(DEPARTMENT, value)

    def set_office(self, value):
        self.set_field(OFFICE, value)

    def set_notification_num(self, value):
        self.set_field(NOTIFICATION_NUM, value)

    def set_partnum(self, value):
        self.set_field(PART_NUM, value)

    def set_refnum(self, value):
        self.set_field(REF_NUM, value)

    def set_linknames(self, value):
        self.set_field(LINK_NAMES, value)

    def set_num(self, value):
        self.set_field(NUM, value)

    def set_gazetteid(self, value):
        self.set_field(GZ_ID, value)

    def set_bundleno(self, value):
        self.set_field(BUNDLE_NO, value)

    def set_city(self, value):
        self.set_field(CITY, value)

    def set_description(self, value):
        self.set_field(DESCRIPTION, value)

    def set_file(self, value):
        self.set_field(FILE, value)

    def set_topic(self, value):
        self.set_field(TOPIC, value)

    def set_year(self, value):
        self.set_field(YEAR, value)

    def set_publisher(self, value):
        self.set_field(PUBLISHER, value)
    
    def set_subdepartment(self, value):
        self.set_field(SUBDEPARTMENT, value)

    def set_doctype(self, value):
        self.set_field(DOCTYPE, value)
    
    def set_category(self, value):
        self.set_field(CATEGORY, value)

    def get_url(self):
        return self.get_field(URL)

    def get_href(self):
        return self.get_field(HREF)

    def get_title(self):
        return self.get_field(TITLE)

    def get_date(self):
        return self.get_field(DATE)

    def get_ministry(self):
        return self.get_field(MINISTRY)

    def get_subject(self):
        return self.get_field(SUBJECT)

    def get_gztype(self):
        return self.get_field(GZTYPE)

    def get_gznum(self):
        return self.get_field(GZNUM)

    def get_department(self):
        return self.get_field(DEPARTMENT)

    def get_office(self):
        return self.get_field(OFFICE)

    def get_notification_num(self):
        return self.get_field(NOTIFICATION_NUM)

    def get_partnum(self):
        return self.get_field(PART_NUM)

    def get_refnum(self):
        return self.get_field(REF_NUM)

    def get_linknames(self):
        return self.get_field(LINK_NAMES)

    def get_num(self):
        return self.get_field(NUM)

    def get_gazetteid(self):
        return self.get_field(GZ_ID)

    def get_bundleno(self):
        return self.get_field(BUNDLE_NO)

    def get_city(self):
        return self.get_field(CITY)

    def get_description(self):
        return self.get_field(DESCRIPTION)

    def get_file(self):
        return self.get_field(FILE)

    def get_topic(self):
        return self.get_field(TOPIC)

    def get_year(self):
        return self.get_field(YEAR)

    def get_publisher(self):
        return self.get_field(PUBLISHER)
    
    def get_subdepartment(self):
        return self.get_field(SUBDEPARTMENT)
    
    def get_doctype(self):
        return self.get_field(DOCTYPE)
    
    def get_category(self):
        return self.get_field(CATEGORY)

def stats_to_message(stats):
    rawstats  = stats[0]
    metastats = stats[1]

    messagelist = ['Stats on documents']
    messagelist.append('======================')
    courtnames = [x['courtname'] for x in rawstats]
    rawnum     = {x['courtname']: x['num'] for x in rawstats}
    metanum    = {x['courtname']: x['num'] for x in metastats}

    for courtname in courtnames:
        if courtname in metanum:
            meta = metanum[courtname]
        else:
            meta = 0
        messagelist.append('%s\t%s\t%s' % (rawnum[courtname], meta, courtname))
 
    return '\n'.join(messagelist)

def get_file_type(filepath):
    mtype = magic.from_file(filepath, mime = True)

    return mtype

def get_buffer_type(buff):
    mtype = magic.from_buffer(buff, mime=True)

    return mtype


def get_file_extension(mtype):
    if re.match('text/html', mtype):
        return 'html'
    elif re.match('application/postscript', mtype):
        return 'ps'
    elif re.match('application/pdf', mtype):
        return 'pdf'
    elif re.match('text/plain', mtype):
        return 'txt'
    elif re.match('image/png', mtype):
        return 'png'
    return 'unkwn'

def setup_logging(loglevel, logfile):
    leveldict = {'critical': logging.CRITICAL, 'error': logging.ERROR, \
                 'warning': logging.WARNING,   'info': logging.INFO, \
                 'debug': logging.DEBUG}

    logfmt  = '%(asctime)s: %(name)s: %(levelname)s %(message)s'
    datefmt = '%Y-%m-%d %H:%M:%S'
    if logfile:
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




