import re
import os
import ssl
import json
import time
import datetime
import urllib.request, urllib.parse, urllib.error
from http.cookiejar import CookieJar

from .basegazette import BaseGazette
from ..utils import utils

class Uttarakhand(BaseGazette):
    def __init__(self, name, storage):
        BaseGazette.__init__(self, name, storage)
        self.baseurl      = 'https://gazettes.uk.gov.in/'
        self.search_endp  = 'searchgazette.aspx'
        self.searchurl    = urllib.parse.urljoin(self.baseurl, self.search_endp)
        self.hostname     = 'gazettes.uk.gov.in'

	
    def get_search_form(self, webpage, endp):
        d = utils.parse_webpage(webpage, self.parser)
        if d == None:
            return None

        search_form = d.find('form', {'action': endp})
        return search_form

    def get_selected_option(self, select):
        option = select.find('option', {'selected': 'selected'})
        if option == None:
            option = select.find('option')
        if option == None:
            return ''
        val = option.get('value')
        if val == None:
            val = ''
        return val

    def get_form_data(self, webpage, dateobj):
        search_form = self.get_search_form(webpage, self.search_endp)
        if search_form == None:
            self.logger.warning('Unable to get the search form for day: %s', dateobj)
            return None 

        formdata = []
        reobj  = re.compile('^(input|select)$')
        inputs = search_form.find_all(reobj)
        for tag in inputs:
            name  = None
            value = None

            if tag.name == 'input':
                name  = tag.get('name')
                value = tag.get('value')
                t     = tag.get('type')
                if t == 'image' or t == 'submit':
                    continue
            elif tag.name == 'select':        
                name = tag.get('name')
                value = self.get_selected_option(tag)
            if name:
                if value == None:
                    value = ''
                formdata.append((name, value))
        return formdata

    def replace_field(self, formdata, k, v):
        newdata = []
        for k1, v1 in formdata:
            if k1 == k:
                newdata.append((k1, v))
            else:
                newdata.append((k1, v1))
        return newdata

    def get_mismatched_field(self, formdata, expected):
        mismatched = None
        for k,v in expected.items():
            if mismatched != None:
                break
            for k1, v1 in formdata:
                if k1 != k:
                    continue
                if v1 != v:
                    mismatched = k
                    break
        return mismatched

    def download_oneday(self, relpath, dateobj):
        dls = []

        cookiejar  = CookieJar()
        response   = self.download_url(self.searchurl, savecookies = cookiejar)
        if not response or not response.webpage:
            self.logger.warning('Could not get base page for date %s', \
                              dateobj)
            return dls

        expected_fields = {
            'ddltodate_date'   : utils.pad_zero(dateobj.day),
            'ddlfromdate_day'  : utils.pad_zero(dateobj.day),
            'ddltodate_mon'    : utils.pad_zero(dateobj.month),
            'ddlfromdate_mon'  : utils.pad_zero(dateobj.month),
            'ddltodate_year'   : utils.pad_zero(dateobj.year),
            'ddlfromdate_year' : utils.pad_zero(dateobj.year),
        }

        formdata = self.get_form_data(response.webpage, dateobj)
        while True:
            field_to_update = self.get_mismatched_field(formdata, expected_fields)
            if field_to_update == None:
                break

            formdata = self.replace_field(formdata, field_to_update, \
                                          expected_fields[field_to_update])
            formdata = self.replace_field(formdata, '__EVENTTARGET', field_to_update)

            response = self.download_url(self.searchurl, savecookies = cookiejar, \
                                       loadcookies = cookiejar, postdata = formdata, \
                                       referer = self.searchurl)
            if not response or not response.webpage:
                self.logger.warning('Could not make call to update field %s for date %s', \
                                    field_to_update, dateobj)
                return dls
            formdata = self.get_form_data(response.webpage, dateobj)

        formdata.append(('Button2', 'Search'))
        response = self.download_url(self.searchurl, savecookies = cookiejar, \
                                   loadcookies = cookiejar, postdata = formdata, \
                                   referer = self.baseurl)
        if not response or not response.webpage:
            self.logger.warning('Could not download search result for date %s', \
                              dateobj)
            return dls

        d = utils.parse_webpage(response.webpage, self.parser)
        if not d:
            self.logger.warning('Could not parse search result for date %s', \
                              dateobj)
            return dls
        
        minfos = self.get_metainfos(d, dateobj)
        for metainfo in minfos:
            if 'url' not in metainfo or 'notification_num' not in metainfo:
                self.logger.warning('Ignoring %s', metainfo)
                continue
            
            filename, n = re.subn('[\s/]+', '_', metainfo['notification_num'])
            relurl = os.path.join(relpath, filename)   
             
            if self.save_gazette(relurl, metainfo['url'], metainfo):
                dls.append(relurl)

        return dls
    
    def get_metainfos(self, d, dateobj):
        minfos = []
        
        order = None
        for table in d.find_all('table'):
            if table.find('table'):
                continue

            for tr in table.find_all('tr'):
                if not order:
                    order = self.get_field_order(tr)
                    continue
                
                metainfo = self.process_row(tr, order, dateobj)
                if metainfo:
                    minfos.append(metainfo)
                       
            if order:
                break

        return minfos
     
    def get_field_order(self, tr):
        order = []
        for td in tr.find_all('td'):
            txt = utils.get_tag_contents(td)
            if txt and re.search('GO\s+No', txt):
                order.append('notification_num')     
            elif txt and re.search('GO\s+Description', txt):
                order.append('subject')     
            elif txt and re.search('Issued\s+by', txt):
                order.append('issued_by')     
            else:
                order.append('')     
       
        if 'notification_num' in order and 'subject' in order and \
                'issued_by' in order:
            return order

        return None                
    
    def process_row(self, tr, order, dateobj):
        metainfo = utils.MetaInfo()
        metainfo.set_date(dateobj)    

        i = 0
        for td in tr.find_all('td'):
            if len(order) > i:
                if order[i] in ['notification_num', 'subject', 'issued_by']:
                    txt = utils.get_tag_contents(td)
                    if txt:
                        metainfo[order[i]] = txt
            i += 1            
        link = tr.find('a')
        if link and link.get('href'):
            href = link.get('href')
            metainfo['url'] = urllib.parse.urljoin(self.searchurl, href)

        return metainfo 

'''
SEARCH API
ID=4519  File=4519-010626110427.pdf  GoDate=23-04-2026

ID=4515  File=4515-010626104148.pdf  GoDate=07-05-2026   ← uploaded June 1
ID=4519  File=4519-010626110427.pdf  GoDate=23-04-2026   ← uploaded June 1, GoDate April 23
ID=4522  File=4522-010626111801.pdf  GoDate=09-04-2026   ← uploaded June 1, GoDate April 9

4519  -  01  06  26  11  04  27  .pdf
 ID      DD  MM  YY  HH  MM  SS
                 ↑
         This is the UPLOAD date (June 1, 2026)
         NOT the gazette date
'''

class UttarakhandBase(BaseGazette):
    def __init__(self, name, storage_manager):
        BaseGazette.__init__(self, name, storage_manager)
        self.baseurl     = 'https://gazettes.uk.gov.in/'
        self.search_endp = 'en/Search/SearchGazette'
        self.gz_id     = '0'                         # default, not indicates any gz id
        self.gz_type   = ''                           # default, not indicates any gz type
        self.cookiejar   = CookieJar()
        self.lookback    = 15

        # gazettes.uk.gov.in requires legacy TLS renegotiation.
        # Build a dedicated SSL context so this doesn't affect other crawlers.
        # Making this global would be overriden by other crawler imports in datasrcs
        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        ctx.check_hostname = False
        ctx.verify_mode    = ssl.CERT_NONE
        ctx.options       |= 0x4  # OP_LEGACY_SERVER_CONNECT
        self._ssl_ctx      = ctx

    def download_url_onetime(self, url, loadcookies, savecookies,
                             postdata, referer, encodepost, headers, fixurl, method):
        from .basegazette import WebResponse
        webresponse = WebResponse()

        if self.backoff > 0:
            time.sleep(self.backoff)

        headers['User-agent'] = self.useragent
        if referer:
            headers['Referer'] = referer

        encodedData = None
        if postdata:
            if encodepost:
                encodedData = urllib.parse.urlencode(postdata).encode('utf-8')
            else:
                encodedData = postdata

        fixed_url = self.url_fix(url) if fixurl else url

        if method is None:
            request = urllib.request.Request(fixed_url, encodedData, headers)
        else:
            request = urllib.request.Request(fixed_url, encodedData, headers, method=method)

        if loadcookies is not None:
            loadcookies.add_cookie_header(request)
            if 'Cookie' in request.unredirected_hdrs:
                request.headers['Cookie'] = request.unredirected_hdrs.pop('Cookie')

        self.logger.debug('Request url: %s headers: %s data: %s',
                          request.full_url, request.headers, request.data)
        try:
            https_handler = urllib.request.HTTPSHandler(context=self._ssl_ctx)
            opener        = urllib.request.build_opener(https_handler)
            response_obj  = opener.open(request, timeout=self.request_timeout_secs)
            response      = response_obj.info()
            webpage       = response_obj.read()

            webresponse.set_webpage(webpage)
            webresponse.set_srvresponse(response)
            webresponse.set_response_url(response_obj.geturl())

            self.logger.info('Url: %s response_url: %s Status: %s',
                             fixed_url, response_obj.geturl(), response_obj.getcode())
        except Exception as e:
            webresponse.set_error(e)
            self.logger.warning('Could not fetch: %s error: %s', url, e)
            return webresponse

        self.logger.debug('Server response: %s', response)

        if 'Set-Cookie' in response:
            cookie = response['Set-Cookie']
            if savecookies is not None and cookie:
                savecookies.extract_cookies(response_obj, request)

        return webresponse
    
    def get_cookies(self):
        url = urllib.parse.urljoin(self.baseurl, 'en/Search/index')
        self.download_url(url, savecookies = self.cookiejar)
    
    def get_payload(self, dateobj):
        date_to_str = dateobj.strftime("%Y-%m-%d")
        payload = {
            'BhagID'        : '',
            'CategoryID'    : '',
            'DepartmentID'  : '',
            'EntryType'     : self.gz_id,
            'fromdate'      : date_to_str,
            'GONo'          : '',
            'SectionID'     : '',
            'Subject'       : '',
            'todate'        : date_to_str,
            'WeekDate2'     : '',
        }
        return payload
    
    def get_search_results(self, payload):
        search_url = urllib.parse.urljoin(self.baseurl, self.search_endp)

        response   = self.download_url(search_url, postdata = payload,\
                                       loadcookies = self.cookiejar, 
                                       savecookies = self.cookiejar)
        
        if (not response) or (not response.webpage):
            return None
        try:
            results = response.webpage.decode('utf-8')
            return json.loads(results)
        
        except Exception as e:
            self.logger.warning('unable to decode the response')
            return None
    
    def extract_metainfo(self, row, dateobj):
        metainfo = utils.MetaInfo()
        metainfo.set_date(dateobj)
        metainfo.set_gztype(self.gz_type)
        notification_num = row.get('GONO','')
        part_num = row.get('BhagNameE', '')
        subject = row.get('SubjectE', '')
        department = row.get('DepartmentNameE', '')
        file_path  = row.get('File_Path_PDF','')
        file_name  = row.get('FileName_PDF', '')
        if notification_num:
            metainfo.set_notification_num(notification_num)
        if part_num and part_num.lower() != 'none':
            metainfo.set_partnum(part_num)
        if subject and subject.lower() != 'none':
            metainfo.set_subject(subject)
        if department and department.lower() != 'none':
            metainfo.set_department(department)
        if file_path and file_path.lower() != 'none':
            metainfo['filepath'] = file_path
        if file_name and file_name.lower() != 'none':
            name, _ = os.path.splitext(file_name)
            metainfo['filename'] = name
        return metainfo

    def get_metainfos(self, results, dateobj):
        metainfos = []
        for row in results:
            metainfos.append(self.extract_metainfo(row, dateobj))
        return metainfos
    
    def download_oneday(self, relpath, dateobj):
        self.get_cookies()
        dls = []
        payload = self.get_payload(dateobj)
        results = self.get_search_results(payload)
        if not results:
            return dls
        
        metainfos = self.get_metainfos(results, dateobj)
        for metainfo in metainfos:
            if 'filepath' in metainfo and 'filename' in metainfo:
                doc_name = metainfo.pop('filename')
                file_path = metainfo.pop('filepath')
                relurl = os.path.join(relpath, doc_name)
                pdf_url = urllib.parse.urljoin(self.baseurl, file_path)
                if self.save_gazette(relurl, pdf_url , metainfo,\
                                      cookiefile = self.cookiejar):
                    dls.append(relurl)
        return dls

class UttarakhandDaily(UttarakhandBase):
    def __init__(self, name, storage_manager):
        UttarakhandBase.__init__(self, name, storage_manager)
        self.gz_id   = '1'
        self.gz_type = 'Daily'

class UttarakhandWeekly(UttarakhandBase):
    def __init__(self, name, storage_manager):
        UttarakhandBase.__init__(self, name, storage_manager)
        self.gz_id   = '2'
        self.gz_type = 'Weekly'