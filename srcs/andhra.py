from http.cookiejar import CookieJar
import re
import os
from datetime import date
import urllib

from ..utils import utils
from .basegazette import BaseGazette
from .central import CentralBase

class AndhraBase(BaseGazette):
    def __init__(self, name, storage):
        BaseGazette.__init__(self, name, storage)

        self.baseurl          = 'https://apegazette.cgg.gov.in'
        self.search_form_url  = urllib.parse.urljoin(self.baseurl, 'searchAllGazette')
        self.searchurl        = urllib.parse.urljoin(self.baseurl, 'searchAllGazettes')
        self.hostname         = 'apegazette.cgg.gov.in'
        self.pdf_download_url = urllib.parse.urljoin(self.baseurl,\
                                                     f'/uploadGazette_view?filePath=%s')

        self.gazette_id       = '0'
        self.table_field      = 'displaytable1'

    def get_field_order(self, tr):
        i = 0
        order  = []
        valid = False
        for th in tr.find_all('th'):
            txt = utils.get_tag_contents(th)
            if txt and re.search('gazette\s*type', txt, re.IGNORECASE):
                order.append('gztype')
            elif txt and re.search('department', txt, re.IGNORECASE):
                order.append('department')
            elif txt and re.search('abstract', txt, re.IGNORECASE):
                order.append('subject')
            elif txt and re.search('Gazette\s+No', txt, re.IGNORECASE):
                order.append('gznum')
            elif txt and re.search('Issue\s+No', txt, re.IGNORECASE):
                order.append('issue_num')
            elif txt and re.search('Notification\s+No', txt, re.IGNORECASE):
                order.append('notification_num')
            elif txt and re.search('Download', txt, re.IGNORECASE):
                order.append('download')
                valid = True
            elif txt and re.search('', txt, re.IGNORECASE):
                order.append('')

            else:
                order.append('')    

            i += 1
        if valid:    
            return order
        return None    

    def get_post_data(self, dateobj, gazette_id, department, \
                      csrf_token):
        datestr = utils.dateobj_to_str(dateobj, '')
        today_date_str = utils.dateobj_to_str(date.today(), '/')

        postdata = [\
            ('_csrf',                  csrf_token), \
            ('mode',                   'unspecified'),  \
            ('hdnCurDate' ,            today_date_str), \
            ('departmentId',           department), \
            ('gazeeteTypeId',          gazette_id), \
            ('gazeetePartId',          ''), \
            ('year',                   ''), \
            ('month1',                 ''), \
            ('fromdate',               datestr), \
            ('todate',                 datestr), \
            ('gazetteno',              ''), \
            ('abstract1',               ''), \
            ('_csrf',                  csrf_token), \
            
        ]
        return postdata

    def parse_search_results(self, webpage, dateobj):
        minfos = []
        d = utils.parse_webpage(webpage, self.parser)
        if not d:
            self.logger.warning('Unable to parse results page for date %s', dateobj)
            return minfos

        table = d.find('table', {'id': self.table_field})
        if not table:
            self.logger.warning('Unable to find result table for date %s', dateobj)
            return minfos
        
        order = None
        for tr in table.find_all('tr'):
            if not order:
                order = self.get_field_order(tr)
                continue
            metainfo = self.parse_row(tr, order, dateobj)
            if metainfo and 'download' in metainfo:
                minfos.append(metainfo)

        return minfos

    def parse_row(self, tr, order, dateobj):
        metainfo = utils.MetaInfo()
        metainfo.set_date(dateobj)

        i = 0
        for td in tr.find_all('td'):
            txt = utils.get_tag_contents(td)
            if i < len(order) and txt:
                txt = txt.strip()
                col = order[i]
                if col == 'gztype':
                    words = txt.split('/')
                    metainfo.set_gztype(words[0].strip())
                    if len(words) > 1:
                        metainfo.set_partnum(words[1].strip())
                    if len(words) > 2:
                        metainfo['district'] = words[2].strip()
                elif col == 'download':
                    inp = td.find('input')       
                    if inp and inp.get('onclick'): 
                        metainfo['download'] = inp.get('onclick')
                elif col in ['notification_num', 'gznum', 'department']:
                    metainfo[col] = txt
                elif col == 'subject':
                    metainfo.set_subject(txt)
            i += 1
        return metainfo

    def get_departments(self, webpage):
        d = utils.parse_webpage(webpage, self.parser)
        if not d:
            return []
        departments = [opt['value'] for opt in d.select('#departmentId option[value]') \
                       if opt['value']]
        return departments
    
    def get_csrf_token(self, webpage):       
        d = utils.parse_webpage(webpage, self.parser)
        if not d:
            return ''
        csrf = d.find('meta', {'name': '_csrf'}).get('content', '')
        return csrf
    
    def download_oneday(self, relpath, dateobj):
        dls = []
        cookiejar  = CookieJar()

        response = self.download_url(self.search_form_url, savecookies = cookiejar)
        if not response or not response.webpage:
            return dls

        departments = self.get_departments(response.webpage)
        csrf_token = self.get_csrf_token(response.webpage)

        if (not departments) or (not csrf_token):
            return dls
        
        for department in departments:
            postdata = self.get_post_data(dateobj, self.gazette_id,  \
                                department, csrf_token)
            response = self.download_url(self.searchurl, postdata = postdata, \
                                loadcookies = cookiejar, savecookies = cookiejar)

            if not response or not response.webpage:
                continue

            metainfos = self.parse_search_results(response.webpage, dateobj)
            for metainfo in metainfos:
                relurl = self.download_metainfo(metainfo, relpath, cookiejar)
                if relurl:
                    dls.append(relurl)

        return dls

    def download_metainfo(self, metainfo, relpath, cookiejar):
        reobj = re.search(r"openDocument\(\s*'(?P<content>[^']*)'\s*\)", metainfo['download'])
        if not reobj:
            return None
        docid = reobj.group('content') 
        
        metainfo.pop('download')
        relurl = os.path.join(relpath, docid.replace('/','-'))
        doc_url = self.pdf_download_url % docid
        if self.save_gazette(relurl, doc_url, metainfo, \
                             cookiefile = cookiejar, \
                             validurl = True):
            return relurl
        return None

class AndhraExtraOrdinary(AndhraBase):
    def __init__(self, name, storage):
        AndhraBase.__init__(self, name, storage)
        self.gazette_id = '1' #extra ordinary's id

class AndhraWeekly(AndhraBase):
    def __init__(self, name, storage):
        AndhraBase.__init__(self, name, storage)
        self.gazette_id = '2' # weekly's id

class AndhraArchive(CentralBase):
    def __init__(self, name, storage):
        CentralBase.__init__(self, name, storage)
        self.baseurl      = 'https://gazettearchive.ap.gov.in/gt_PublicReport.aspx'
        self.hostname     = 'gazettearchive.ap.gov.in'
        self.search_endp  = 'gt_PublicReport.aspx'
        self.result_table = 'FileMoveList2'

    def get_search_results(self, search_url, dateobj, cookiejar):
        response = self.download_url(search_url, savecookies = cookiejar, loadcookies=cookiejar)

        postdata = self.get_form_data(response.webpage, dateobj, self.search_endp)
        if postdata == None:
            return None
        response = self.download_url(search_url, savecookies = cookiejar, \
                                   loadcookies = cookiejar, postdata = postdata)
        return response

    def get_post_data(self, tags, dateobj):
        datestr  = utils.dateobj_to_str(dateobj, '')
        postdata = []

        for tag in tags:
            name  = None
            value = None

            if tag.name == 'input':
                name  = tag.get('name')
                value = tag.get('value')
                t     = tag.get('type')
                if t == 'image' or name == 'Button2' or name == 'Button1':
                    continue


                if name == 'txttodate' or name == 'txtfrmdate':
                    value = datestr
                elif name in ['jobno', 'txtGoNo', 'txtSearchText']:
                    value = ''
            elif tag.name == 'select':
                name = tag.get('name')
                if name == 'BtnSearch':
                    value = 'search'
                elif name == 'DDLDeptname':
                    value = 'Select'
                elif name == 'DDLGoType':
                    value = 'Select'
                elif name == 'DropDownList1':
                    value = 'Select'

            if name:
                if value == None:
                    value = ''
                postdata.append((name, value))

        return postdata

    def get_column_order(self, tr):
        order = []
        for th in tr.find_all('th'):
            txt = utils.get_tag_contents(th)
            if txt and re.search('GazetteType', txt):
                order.append('gztype')
            elif txt and re.search('Abstract', txt):
                order.append('subject')
            elif txt and re.search('DepartmentName', txt):
                order.append('department')
            elif txt and re.search('Gazette\s+No', txt):
                order.append('gznum')
            elif txt and re.search('Issued\s+By', txt):
                order.append('issued_by')
            else:
                order.append('')
        return order

    def process_result_row(self, tr, metainfos, dateobj, order):
        download = None
        for link in tr.find_all('a'):
            txt = utils.get_tag_contents(link)
            if txt and re.match('\s*select', txt, re.IGNORECASE):
                download = link.get('href')
                break
 
        if not download:
            return
 
        metainfo = utils.MetaInfo()
        metainfos.append(metainfo)
        metainfo.set_date(dateobj)
        metainfo['download'] = download

        i = 0
        for td in tr.find_all('td'):
            if len(order) > i:
                col = order[i]
                txt = utils.get_tag_contents(td)
                if txt:
                    txt = txt.strip()
                else:
                    continue

                if col == 'gztype':
                    pos = txt.find('PART')
                    if pos > 0:
                        metainfo.set_gztype(txt[:pos])
                        metainfo['partnum'] = txt[pos:]
                    else:
                        metainfo.set_gztype(txt)

                elif col in ['subject', 'department', 'issued_by', 'gznum']:
                    metainfo[col] = txt
  
            i += 1

    def download_metainfos(self, relpath, metainfos, search_url, \
                           postdata, cookiejar):
        dls = []
        for metainfo in metainfos:
            if 'download' not in metainfo or 'gznum' not in metainfo:
                self.logger.warning('Required fields not present. Ignoring- %s' % metainfo) 
                continue

            href = metainfo.pop('download')
            reobj = re.search('javascript:__doPostBack\(\'(?P<event_target>[^\']+)\',\'(?P<event_arg>[^\']+)\'\)', href)
            if not reobj:
                self.logger.warning('No event_target or event_arg in the gazette link. Ignoring - %s' % metainfo)
                continue 

            groupdict    = reobj.groupdict()
            event_target = groupdict['event_target']
            event_arg    = groupdict['event_arg']

            newpost = []
            for t in postdata:
                if t[0] == 'BtnSearch':
                    continue
                if t[0] == '__EVENTTARGET':
                    t = (t[0], event_target)
                if t[0] == '__EVENTARGUMENT':
                    t = (t[0], event_arg)

                newpost.append(t)
                   
            gznum = metainfo['gznum']
            if 'partnum' in metainfo:
                gznum = '%s_%s' % (gznum, metainfo['partnum'])
            gznum, n = re.subn('[\s]+', '', gznum)
            relurl = os.path.join(relpath, gznum)
            if self.save_gazette(relurl, search_url, metainfo, \
                                 postdata = newpost, cookiefile = cookiejar, \
                                 validurl = False):
                dls.append(relurl)

        return dls
