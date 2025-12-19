import re
import os
import urllib.parse
import datetime

import requests
from requests.adapters import HTTPAdapter

from ..utils import utils
from .basegazette import BaseGazette

class JammuAndKashmir(BaseGazette):
    def __init__(self, name, storage):
        BaseGazette.__init__(self, name, storage)
        self.baseurl  = 'https://rgp.jk.gov.in/gazette.html'
        self.hostname = 'rgp.jk.gov.in'
        self.page_cache = {}
        self.session = None

    def get_session(self):
        s = requests.session()
        retry = self.get_session_retry()
        s.mount('http://', HTTPAdapter(max_retries=retry, pool_maxsize=1))
        s.mount('https://', HTTPAdapter(max_retries=retry, pool_maxsize=1))
        return s

    def download_url(self, url, loadcookies = None, savecookies = None, \
                     postdata = None, referer = None, \
                     encodepost= True, headers = {}):
        if self.session is None:
            self.session = self.get_session()

        return self.download_url_using_session(url, session = self.session, postdata = postdata, \
                                   referer = referer, headers = headers) 


    def download_url_cached(self, url):

        if url not in self.page_cache:
            response = self.download_url(url)

            self.page_cache[url] = response

        return self.page_cache[url]
 
    def clean_string(self, txt):
        txt = ' '.join(txt.splitlines())
        txt = ' '.join(txt.split())
        txt = txt.strip()
        return txt
    
    def get_year_urls(self, year):
        year_urls = []

        year_short = year - 2000
        gazette_strings = [ 
            f'Gazettes20{year_short}-{year_short+1}',
            f'Gazettes20{year_short-1}-{year_short}',
        ]

        response = self.download_url_cached(self.baseurl)
        if response is None and response.webpage is None:
            self.logger.warning('Unable to get %s', self.baseurl)
            return year_urls

        d = utils.parse_webpage(response.webpage, self.parser)
        if d is None:
            self.logger.warning('Unable to parse %s', self.baseurl)
            return year_urls

        div = d.find('div', {'id': 'MainText'})
        if div is None:
            self.logger.warning('Unable to locate main div for %s', self.baseurl)
            return year_urls

        for para in div.find_all('p'):
            txt = utils.get_tag_contents(para)
            txt = txt.strip()
            txt = self.clean_string(txt)
            txt = txt.replace(' ', '')
            if txt in gazette_strings:
                link = para.find('a')
                if link:
                    href = link.get('href')
                    year_urls.append(urllib.parse.urljoin(self.baseurl, href))

        return year_urls

    def get_metainfos(self, webpage, url):
        metainfos = []
        d = utils.parse_webpage(webpage, self.parser)
        if d is None:
            self.logger.warning('Unable to parse %s', url)
            return metainfos

        div = d.find('div', {'id': 'MainText-right'})
        if div is None:
            self.logger.warning('Unable to locate main div for %s', url)
            return metainfos

        for link in div.find_all('a'):
            href = link.get('href')
            if href is None:
                continue

            txt = utils.get_tag_contents(link)
            txt = self.clean_string(txt)
            if txt == '':
                continue
            # Gazette No. 41 dated 12th Jan., 2017
            reobj = re.search(r'Gazette\s+No(\.)?\s*(?P<num>\d+)\s+dated\s+(?P<day>\d+)\s*(rd|th|st|nd)?\s+(?P<month>\w+)[ \.,]*(?P<year>\d+)', txt)
            if reobj is None:
                self.logger.warning('Unable to parse link text %s', txt)
                continue
            g = reobj.groupdict()
            try:
                issuedate = datetime.datetime.strptime(f'{g["day"]}-{g["month"][:3]}-{g["year"]}', '%d-%b-%Y').date()
            except Exception:
                self.logger.warning('Unable to create date from %s', g)
                continue

            metainfo = utils.MetaInfo()
            metainfo.set_date(issuedate)
            metainfo['gznum']    = g['num']
            metainfo['download'] = urllib.parse.urljoin(url, href)
            metainfos.append(metainfo)

        return metainfos


    def download_section(self, dls, relpath, url, dateobj):
        response = self.download_url_cached(url)
        if response is None or response.webpage is None:
            self.logger.warning('Unable to get %s for %s', url, dateobj)
            return

        metainfos = self.get_metainfos(response.webpage, url)

        for metainfo in metainfos:
            if metainfo.get_date() != dateobj:
                continue

            gzurl = metainfo.pop('download')
            if gzurl.endswith('.html'):
                continue

            relurl = os.path.join(relpath, metainfo['gznum'])
            if self.save_gazette(relurl, gzurl, metainfo):
                dls.append(relurl)


    def download_oneday(self, relpath, dateobj):
        dls = []

        year_urls = self.get_year_urls(dateobj.year)

        for year_url in year_urls:
            self.download_section(dls, relpath, year_url, dateobj)
        
        return dls