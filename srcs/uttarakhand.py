import re
import os
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
