import re
import os
import datetime
import urllib
from cookielib import CookieJar

from basegazette import BaseGazette
import utils

class Uttarakhand(BaseGazette):
    def __init__(self, name, storage):
        BaseGazette.__init__(self, name, storage)
        self.baseurl      = 'http://gazettes.uk.gov.in/'
        self.search_endp  = 'searchgazette.aspx'
        self.searchurl    = urllib.basejoin(self.baseurl, self.search_endp)
        self.hostname     = 'gazettes.uk.gov.in'
        self.start_date   = datetime.datetime(2013, 1, 1)

    def find_search_form(self, d):
        search_form = None
        forms = d.find_all('form')
        for form in forms:
            action = form.get('action')
            if action == './%s' % self.search_endp or action == self.search_endp:
                search_form = form
                break

        return search_form
	
    def get_post_data(self, tags, dateobj):
        postdata = []
        today    = datetime.date.today()

        for tag in tags:
            name  = None
            value = None

            if tag.name == 'input':
                name  = tag.get('name')
                value = tag.get('value')
                t     = tag.get('type')
                if t == 'image':
                    continue

                if name in['btnGono', 'btnOfficeName', 'btnreset']:
                    continue

            elif tag.name == 'select':        
                name = tag.get('name')
                if name == 'ddloffcode':
                    value = '0'
                elif name == 'ddlcatcode': 
                    value = '0'
                elif name == 'ddldeptcode':
                    value = 'All Department'
                elif name == 'ddlgodatefrom' or name == 'ddlgodateto':
                    value = utils.pad_zero(dateobj.day)
                elif name == 'ddlgomonfrom' or name == 'ddlgomonto':
                    value = utils.pad_zero(dateobj.month)
                elif name == 'ddlgoyearfrom' or name == 'ddlgoyearto':
                    value = utils.pad_zero(dateobj.year)
                elif name == 'ddlfromdate_day' or name == 'ddlfromdate_mon':
                    value = '01'
                elif name == 'ddlfromdate_year':
                    value = '2013'
                elif name == 'ddltodate_date':
                    value = utils.pad_zero(today.day)
                elif name == 'ddltodate_mon':
                    value = utils.pad_zero(today.month)
                elif name == 'ddltodate_year':
                    value = utils.pad_zero(today.year)

            if name:
                if value == None:
                    value = u''
                postdata.append((name, value))

        return postdata

    def get_search_form(self, webpage, dateobj):
        if webpage == None:
            self.logger.warn('Unable to download the starting search page for day: %s', dateobj)
            return None 

        d = utils.parse_webpage(webpage, self.parser)
        if d == None:
            self.logger.warn('Unable to parse the search page for day: %s', dateobj)
            return None

        search_form = self.find_search_form(d)
        return search_form

    def get_form_data(self, webpage, dateobj):
        search_form = self.get_search_form(webpage, dateobj)
        if search_form == None:
            self.logger.warn('Unable to get the search form for day: %s', dateobj)
            return None 

        reobj  = re.compile('^(input|select)$')
        inputs = search_form.find_all(reobj)
        postdata = self.get_post_data(inputs, dateobj)

        return postdata

    def download_oneday(self, relpath, dateobj):
        dls = []

        cookiejar  = CookieJar()
        response   = self.download_url(self.baseurl, savecookies = cookiejar)

        postdata = self.get_form_data(response.webpage, dateobj)
        if postdata == None:
            return dls 

        response = self.download_url(self.searchurl, savecookies = cookiejar, \
                                   loadcookies = cookiejar, postdata = postdata)
        if not response or not response.webpage:
            self.logger.warn('Could not download search result for date %s', \
                              dateobj)
            return dls
        
        d = utils.parse_webpage(response.webpage, self.parser)
        if not d:
            self.logger.warn('Could not parse search result for date %s', \
                              dateobj)
            return dls
        
        minfos = self.get_metainfos(d, dateobj)
        for metainfo in minfos:
            if 'url' not in metainfo or 'notification_num' not in metainfo:
                self.logger.warn('Ignoring %s', metainfo)
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
            metainfo['url'] = urllib.basejoin(self.searchurl, href)

        return metainfo 
