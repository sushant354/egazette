import re

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

    def get_ia_description(self):
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
          ('bundleno',         'Bundle Number'), \
          ('city',             'City'), \
          ('description',      'Description'), \
          ('file',             'File'), \
          ('topic',            'Topic'), \
          ('year',             'Year'), \
          ('title',            'Title')
        ]

        member_keys = set(self.keys())
        for k, kdesc in keys:
             if k not in member_keys:
                 continue

             v = self.get(k)
             if k == 'date':
                 v = f'{v}'
             elif k == 'linknames':
                linkids = self.get('linkids')
                i = 0
                v = []
                for linkname in self.get(k):
                    identifier = linkids[i]
                    v.append(f'<a href="/details/{identifier}">{linkname}</a>')
                    i += 1
                v = '<br/>'.join(v)
             elif k == 'url':
                v = f'<a href="{v}">URL</a>'
             else:    
                 v = self.get(k).strip()
                 
             if v:
                 desc.append((kdesc, v))

        known_keys = set([k for k, kdesc in keys])

        for k, v in self.items():
            if k not in known_keys and k not in ignore_keys:
                if type(v) in (str,):
                    v = v.strip()
                elif isinstance(v, list):
                    v = f'{v}'
                if v:
                    desc.append((k.title(), v))


        desc_html = '<br/>'.join([f'{d[0]}: {d[1]}' for d in desc])
        return f'<p>{desc_html}</p>'

    def get_ia_title(self, srcinfo):
        category = srcinfo['category']
        title = [category]

        dateobj = self.get_date()
        if dateobj is not None:
            title.append(f'{dateobj}')

        gztype = self.get_gztype()
        if gztype is not None:
            title.append(gztype)

        partnum = self.get_partnum()
        if partnum is not None:
            if re.search(r'\bPart\b', partnum):
                title.append(partnum)
            else:    
                title.append(f'Part {partnum}')

        gznum = self.get_gznum()
        if gznum is not None:
            title.append(f'Number {gznum}')

        return ', '.join(title)

    def get_ia_metadata(self, srcinfo):
        creator   = srcinfo['source']
        category  = srcinfo['category']
        languages = srcinfo['languages']

        collection = srcinfo.get('collection', 'gazetteofindia')

        title = self.get_ia_title(srcinfo)

        metadata = { \
            'mediatype' : 'texts', 'language' : languages, \
            'title'     : title,   'creator'  : creator, \
            'subject'   : category
        }

        if collection != '':
            metadata['collection'] = collection

        dateobj = self.get_date()
        if dateobj:
            metadata['date'] = f'{dateobj}'

        metadata['description'] = self.get_ia_description()
        return metadata

