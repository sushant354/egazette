import re
import os
import urllib.request, urllib.parse, urllib.error
from http.cookiejar import CookieJar
from datetime import datetime, date

from ..utils import utils
from .basegazette import BaseGazette


class Odisha(BaseGazette):
    def __init__(self, name, storage):
        BaseGazette.__init__(self, name, storage)
        self.ordinary_url = 'https://govtpress.odisha.gov.in/odisha-gazettes'
        self.extraordinary_url = 'https://govtpress.odisha.gov.in/ex-ordinary-gazettes'
        self.hostname = 'govtpress.odisha.gov.in'

    def get_post_data(self, webpage, dateobj, srcurl):
        d = utils.parse_webpage(webpage, self.parser)
        if d == None:
            self.logger.warning('Unable to parse page for %s', dateobj)        
            return None
        search_form = d.find('form', { 'action': srcurl })
        if search_form == None:
            self.logger.warning('Unable to find form for %s', dateobj)        
            return None
        reobj  = re.compile('^(input|select|button)$')
        inputs = search_form.find_all(reobj)
        datestr  = datetime.strftime(dateobj, '%Y-%m-%d')
        postdata = []

        for tag in inputs:
            name  = tag.get('name')
            value = tag.get('value')
            if name == 'gazette_date':
                value = datestr
            if name:
                if value == None:
                    value = ''
                postdata.append((name, value))
        return postdata

    def find_field_order(self, tr):
        order  = []
        for td in tr.find_all('td'):
            txt = utils.get_tag_contents(td)
            if txt and re.search('Department', txt):
                order.append('department')
            elif txt and re.search('Notification\s+No', txt):
                order.append('notification_num')
            elif txt and re.search('Gazette\s+No', txt):
                order.append('gznum')
            elif txt and re.search('Download', txt):
                order.append('download')
            elif txt and re.search('Gazette\s+Date', txt):
                order.append('gzdate')
            elif txt and re.search('Week\s+No', txt):
                order.append('week_num')
            elif txt and re.search('Remarks', txt):
                order.append('remarks')
            else:
                order.append('')
        
        for field in ['download', 'gzdate', 'gznum']:
            if field not in order:
                return None
        return order
                
    def process_row(self, tr, order, dateobj, gztype):
        metainfo = utils.MetaInfo()
        metainfo.set_gztype(gztype)
        metainfo.set_date(dateobj)
        i = 0
        for td in tr.find_all('td'):
            if len(order) > i:
                txt = utils.get_tag_contents(td)
                txt = txt.strip()
                if order[i] in ['gznum', 'department', 'notification_num', 'week_num', 'remarks']:
                    metainfo[order[i]] = txt
                elif order[i] == 'gzdate':
                    nums = re.findall('\d+', txt)
                    if len(nums) == 3:
                        try:
                            d = date(int(nums[0]), int(nums[1]), int(nums[2]))
                            metainfo['gzdate'] = d
                        except:
                            self.logger.warning('Unable to form date for %s', txt)
                elif order[i] == 'download':
                    link = td.find('a')
                    if link and link.get('href'):
                        metainfo['href'] =  link.get('href')

            i += 1
        if 'href' in metainfo and 'gznum' in metainfo:
            return metainfo
        return None
                
    def download_onetype(self, relpath, dateobj, srcurl, gztype):
        dls = []
        cookiejar = CookieJar()
        response = self.download_url(srcurl, savecookies = cookiejar)
        if response == None or response.webpage == None:
            self.logger('Unable to get the base page for %s date %s', gztype, dateobj)
            return dls
        postdata = self.get_post_data(response.webpage, dateobj, srcurl)
        response = self.download_url(srcurl, postdata = postdata, \
                                     loadcookies = cookiejar, savecookies = cookiejar) 
        if not response or not response.webpage:
            self.logger.warning('Unable to get result page for %s date %s', gztype, dateobj)
            return dls

        d = utils.parse_webpage(response.webpage, self.parser)
        if not d:
            self.logger.warning('Unable to parse result page for %s date %s', gztype, dateobj)
            return dls

        result_table = None
            
        for table in d.find_all('table'):
            for tr in table.find_all('tr'):
                order = self.find_field_order(tr)
                if order:
                    result_table = table
                    break
                 
        if result_table == None:
            self.logger.warning('Unable to find the result table for %s date %s', gztype, dateobj)
            return dls

        minfos = []
        for tr in result_table.find_all('tr'):
            if tr.find('a') == None:
                continue
            metainfo = self.process_row(tr, order, dateobj, gztype)
            if metainfo:
                minfos.append(metainfo)
        
                    
        for metainfo in minfos:
            href   = metainfo.pop('href')
            url    = urllib.parse.urljoin(srcurl, href)
            relurl = os.path.join(relpath, metainfo['gznum'])
            if self.save_gazette(relurl, url, metainfo):
                dls.append(relurl)

        return dls        

    def download_oneday(self, relpath, dateobj):
        odls = self.download_onetype(relpath, dateobj, self.ordinary_url, 'Ordinary')
        edls = self.download_onetype(relpath, dateobj, self.extraordinary_url, 'Extraordinary')
        return odls + edls


class Odisha1(BaseGazette):
    def __init__(self, name, storage):
        BaseGazette.__init__(self, name, storage)
        self.ordinary_url = 'https://ogpress.nic.in/odishagazettes.php'
        self.extraordinary_url = 'https://ogpress.nic.in/ex_odishagazettes.php'
        self.hostname = 'ogpress.nic.in'

    def find_field_order(self, tr, header_type):
        order = []
        for td in tr.find_all(header_type):
            txt = utils.get_tag_contents(td)
            if txt and re.search('Gazette\s+Number', txt):
                order.append('gznum')
            elif txt and re.search('Department', txt):
                order.append('department')
            elif txt and re.search('Gazette\s+Date', txt):
                order.append('gzdate')
            elif txt and re.search('Action', txt):
                order.append('download')
            elif txt and re.search('File', txt):
                order.append('file')
            else:
                order.append('')

        for field in ['download', 'gznum', 'gzdate']:
            if field not in order:
                return None
        return order

    def process_result_row(self, tr, dateobj, gztype, datefmt, order):
        metainfo = utils.MetaInfo()
        metainfo.set_gztype(gztype)
        metainfo.set_date(dateobj)
        gzdate = None
        filename = None
        i = 0
        for td in tr.find_all('td'):
            if len(order) > i:
                col = order[i]
                txt = utils.get_tag_contents(td)
                if txt:
                    txt = txt.strip()
                if col in ['gznum', 'department']:
                    metainfo[col] = txt
                elif col == 'gzdate':
                    gzdate = txt
                elif col == 'file':
                    filename = txt
                elif col == 'download':
                    link = td.find('a')
                    if link and link.get('href'):
                        metainfo['href'] =  link.get('href')    
            i += 1

        if gztype == 'Weekly':
            if filename == None or not filename.endswith('.pdf'):
                return None

        try:
            gzdateobj = datetime.strptime(gzdate, datefmt).date()
        except ValueError:
            #self.logger.warning('encountered unparsable date %s', gzdate)
            return None
        if gzdateobj != dateobj:
            return None
        return metainfo

    def download_onetype(self, relpath, dateobj, srcurl, gztype, datefmt, header_type):
        dls = []

        response = self.download_url(srcurl)
        if not response or not response.webpage:
            self.logger.warning('Unable to get result page for type %s for date %s', gztype, dateobj)
            return dls

        d = utils.parse_webpage(response.webpage, self.parser)
        if not d:     
            self.logger.warning('Unable to parse result page for type %s date %s', gztype, dateobj)
            return dls

        result_table = None
            
        for table in d.find_all('table'):
            for tr in table.find_all('tr'):
                order = self.find_field_order(tr, header_type)
                if order:
                    result_table = table
                    break
                 
        if result_table == None:
            self.logger.warning('Unable to find the result table for type %s date %s', gztype, dateobj)
            return dls

        minfos = []
        for tr in result_table.find_all('tr'):
            if tr.find('a') == None:
                continue
            metainfo = self.process_result_row(tr, dateobj, gztype, datefmt, order)
            if metainfo:
                minfos.append(metainfo)

        for metainfo in minfos:
            href   = metainfo.pop('href')
            url    = urllib.parse.urljoin(srcurl, href)
            relurl = os.path.join(relpath, metainfo['gznum'])
            if self.save_gazette(relurl, url, metainfo, validurl = False):
                dls.append(relurl)

        return dls


    def download_oneday(self, relpath, dateobj):
        odls = self.download_onetype(relpath, dateobj, self.ordinary_url, 'Ordinary', '%Y-%m-%d', 'td')
        edls = self.download_onetype(relpath, dateobj, self.extraordinary_url, 'Extraordinary', '%d-%m-%Y', 'th')
        return odls + edls



