import os
import re
import urllib.parse
from http.cookiejar import CookieJar

from .basegazette import BaseGazette
from ..utils import utils

PATTERN = r"Volume No\s+([^\s/]+)\s*/Issue\s+No\s+([\w()]+)\s+of\s+(\d{4})"
GZNUM = "gznum"
YEAR = "year"

class Mizoram(BaseGazette):
    def __init__(self, name, storage_manager):
        BaseGazette.__init__(self, name, storage_manager)
        self.baseurl     = 'https://www.mizoramassembly.in'
        self.gazette_url = urllib.parse.urljoin(self.baseurl,'/gazette')
        self.cookiejar   = CookieJar()

    def sync(self, fromdate, todate, event):
        newdownloads = []

        from_year = fromdate.year
        to_year   = todate.year

        for year in range(from_year, to_year+1):
            if event.is_set():
                self.logger.warning('Exiting prematurely as timer event is set.')
                break

            self.logger.info('Year %s', year)

            tmprel = os.path.join(self.name, str(year))
            dls = self.download_oneyear(tmprel, year)
            self.logger.info('Got %d gazettes for year %s.' % (len(dls), year))
            newdownloads.extend(dls)

        return newdownloads
    
    def get_cookies(self):
        self.download_url(self.baseurl, savecookies = self.cookiejar)
    
    def parse_token(self, webpage):
        token = None
        parsed_webpage = self.parse_webpage(webpage)
        if parsed_webpage:
            inputs = parsed_webpage.select('form > input')
            for inp in inputs:
                name = inp.get('name')
                if name and name == '_token':
                    val = inp.get('value')
                    if val:
                       token = val
                       break
        self.logger.debug(f"Token:{token}.")
        return token

    def get_webpage(self, url, referer = None, postdata = None, encodepost = False, fixurl = True):
        response = self.download_url(
                url,
                loadcookies=self.cookiejar,
                savecookies=self.cookiejar,
                referer=referer,
                postdata = postdata,
                encodepost = encodepost,
                fixurl = fixurl
            )
        if response:
            webpage = response.webpage
        if not webpage:
            self.logger.error(f'web page not found for url : {url}.')
            return None 
        return webpage
    
    def get_token(self):
        referer = urllib.parse.urljoin(self.baseurl, "/")
        webpage = self.get_webpage(self.gazette_url, referer = referer)
        if webpage:
            return self.parse_token(webpage)
        return None

    def download_oneyear(self, relpath, year):
        self.get_cookies()
        token = self.get_token()
        newdls = []
        gazette_types = ['General', 'Extra Ordinary', 'Zoram Hriattirna']
        if not token:
            self.logger.warning('Could not process, token not available.')
        else:
            for type in gazette_types:
                dls = self.download_gazette(type, token, year, relpath)
                self.logger.debug(f"Got {len(dls)} gazettes for type-{type}, year-{year}.")
                newdls.extend(dls)

        return newdls
    
    def encode_url(self, gazette_url, payload):
        encode_data = urllib.parse.urlencode(payload)
        url = urllib.parse.urljoin(gazette_url,f"?{encode_data}")
        return url
    
    def download_gazette(self, gazette_type, token, year, relpath):
        postdata = {
            '_token'       : token,
            'gazette_type' : gazette_type,
            'year'         : year
        }

        url = self.encode_url(self.gazette_url,postdata)
        webpage = self.get_webpage(url = url,fixurl = False)
        dls = self.result_page(webpage, gazette_type, relpath, year)
        return dls

    def parse_webpage(self, webpage):
        parser = 'html.parser'
        parse_result = utils.parse_webpage(webpage, parser)

        return parse_result
    
    def result_page(self, webpage, gazette_type, relpath, year):
        newdls = []

        if not webpage:
            return newdls

        parsed_webpage = self.parse_webpage(webpage)
        trs = parsed_webpage.select('tbody > tr')

        if not trs:
            return newdls
    
        for tr in trs:
            dls =  self.handle_link(tr, gazette_type, relpath, year)
            if dls:
                newdls.append(dls)
        
        next_page = parsed_webpage.select_one("nav ul li a[rel='next']")
        if next_page:
            next_page_url = next_page.get('href')
            if next_page_url:
                next_webpage = self.get_webpage(next_page_url, fixurl = False)
                dls = self.result_page(next_webpage, gazette_type, relpath, year)
                if dls:
                    newdls.extend(dls)
        return newdls
    
    def parse_metainfo(self,tr):
        metainfo = utils.MetaInfo()

        tds = tr.find_all('td')
        gurl = None
        for i, td in enumerate(tds):
            c = utils.get_tag_contents(td).strip()
            a_tag = td.find('a', href=True)
            if c:
                if i == 0:
                    metainfo.set_gznum(c)
                elif i == 1:
                    metainfo.set_title(c)
                elif i == 2:
                    metainfo.set_gztype(c)
                elif i == 3 and a_tag:
                    gurl = a_tag['href']
                    
        return metainfo, gurl
    
    def get_filename(self, gznum):
        match = re.search(PATTERN, gznum)

        if match:
            volume_no = match.group(1)
            issue_no =  match.group(2)
            year = match.group(3)
        filename = volume_no + "-" + issue_no + "-" + year
        return filename
        
    def handle_link(self, tr, gazette_type, relpath, year):
        metainfo, gurl = self.parse_metainfo(tr)
        metainfo.set_year(year)
        filename = gazette_type + "-" + self.get_filename(metainfo.get("gznum"))
        tmprel = os.path.join(relpath,filename)

        if gurl and self.save_gazette(relurl = tmprel, gurl = gurl, metainfo = metainfo):
            return tmprel

        return None



        



