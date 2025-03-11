from http.cookiejar import CookieJar
import re
import os
import urllib.parse

from ..utils import utils
from ..utils.metainfo import MetaInfo
from .basegazette import BaseGazette

class Manipur(BaseGazette):
    def __init__(self, name, storage_manager):
        BaseGazette.__init__(self, name, storage_manager)
        self.baseurl     = 'https://manipurgovtpress.nic.in'
        self.search_url =  urllib.parse.urljoin(self.baseurl, 'en/date_filter_list/')
        self.cookiejar = CookieJar()
    
    def get_cookies(self):
        self.download_url(self.baseurl, savecookies = self.cookiejar)
        
    def get_csrf_token(self):
        token = ''
        response =  self.download_url(self.search_url, loadcookies = self.cookiejar,\
                                      savecookies = self.cookiejar)
        if not response or not response.webpage:
            return token
        
        d = utils.parse_webpage(response.webpage, self.parser)
        if not d:
            return token

        token_elem = d.find('input' , { 'name': 'csrfmiddlewaretoken'})
        if token_elem and token_elem.has_attr('value'):
            token = token_elem['value'].strip()

        return token
    
    def get_payload(self, dateobj, csrf_token):
        formatted_date = dateobj.strftime("%Y-%m-%d")
        payload = {
        'csrfmiddlewaretoken'	: csrf_token,
        'start_date' :	formatted_date,
        'end_date' :	formatted_date,
        }
        return payload
    
    def extract_table(self, result):
        d = utils.parse_webpage(result, self.parser)
        if not d:
            return []
        table = d.find('table')
        return table

    def extract_metainfos(self, row, order):
        metainfo = MetaInfo()
        i = 0
        for td in row.find_all('td'):
            if len(order) > i:
                txt = utils.get_tag_contents(td)
                txt = txt.strip()
                if order[i] == 'gznum':
                    metainfo.set_gznum(txt)
                elif order[i] == 'gztype':
                    metainfo.set_gztype(txt)  
                elif order[i] == 'title':
                    metainfo.set_title(txt)
                    link = td.find('a')
                    if link and link.get('href'):
                        metainfo['href'] =  link.get('href')    

            i += 1
        
        if 'href' in metainfo and 'gznum' in metainfo:
            return metainfo
        return None
    
    def get_column_order(self, table):
        ths = table.select('tr > th')
        order = []
        for th in ths:
            txt = utils.get_tag_contents(th)
            if txt and re.search('Gazette\s*Number', txt):
                order.append('gznum')
            elif txt and re.search('Gazette\s*Type', txt):
                order.append('gztype')
            elif txt and re.search('Gazzete\s*Title', txt):
                order.append('title')
            else:
                order.append('')
        return order

    def get_metainfos(self, result):
        table = self.extract_table(result)
        order = self.get_column_order(table)
        rows = table.select('tr:has(td)')
        
        metainfos = []
        
        for row in rows:
            metainfo = self.extract_metainfos(row, order)
            if metainfo:
                metainfos.append(metainfo)
        
        return metainfos
        
    def get_search_results(self, dateobj, csrf_token):
        metainfos = []
        payload = self.get_payload(dateobj, csrf_token)
        response = self.download_url(self.search_url, postdata = payload,
                                    loadcookies = self.cookiejar,\
                                    savecookies = self.cookiejar,
                                    referer = self.search_url,
                                    headers = {
                                        'Content-Type' : 'application/x-www-form-urlencoded' 
                                    })
        
        if not response or not response.webpage:
            return metainfos
        
        metainfos = self.get_metainfos(response.webpage)
        return metainfos

    def download_gazette(self, pdf_url, relurl, metainfo):
        response = self.download_url(pdf_url, loadcookies = self.cookiejar,\
                                     savecookies = self.cookiejar)
        if not response or not response.webpage:
            return False

        d = utils.parse_webpage(response.webpage, self.parser)
        if not d:
            return False
        
        link = d.find("a", href=True, download=True)
        if not link:
            return False
        
        href = link['href']
        url = urllib.parse.urljoin(self.baseurl, href)
        if self.save_gazette(relurl, url, metainfo, cookiefile = self.cookiejar):
            return True
        
        return False

    def download_oneday(self, relpath, dateobj):
        dls = []
        csrf_token = self.get_csrf_token()
        if not csrf_token:
            return dls
         
        metainfos = self.get_search_results(dateobj, csrf_token)
        
        for metainfo in metainfos:
            metainfo.set_date(dateobj)
            relurl  = os.path.join(relpath, metainfo.get_gznum())
            href = metainfo.pop('href')
            pdf_url = urllib.parse.urljoin(self.baseurl, href)
            if self.download_gazette(pdf_url, relurl, metainfo):
                dls.append(relurl)
        
        return dls