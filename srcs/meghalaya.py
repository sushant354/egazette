import re
import os
import urllib.parse

from ..utils import utils
from .basegazette import BaseGazette
import datetime

class Meghalaya(BaseGazette):
    def __init__(self, name, storage):
        BaseGazette.__init__(self, name, storage)
        self.baseurl = 'https://megpns.gov.in/gazette/archive.asp?wdate={}&wmonth={}&datepub={}'
        self.hostname = 'megpns.gov.in'

    def parse_results(self, webpage, dateobj):
        metainfos = []

        d = utils.parse_webpage(webpage, self.parser)
        if d is None:
            self.logger.warning('Unable to parse result page for %s', dateobj)
            return metainfos

        article = d.find('article')
        if article is None:
            return metainfos

        for li in article.find_all('li'):
            link = li.find('a')
            if not link:
                continue

            href = link.get('href')
            if href is None:
                continue

            subject = utils.get_tag_contents(link)
            subject = subject.strip()

            metainfo = utils.MetaInfo()
            metainfo.set_date(dateobj)
            metainfo['subject']  = subject
            metainfo['download'] = href
            metainfos.append(metainfo)

        return metainfos

    def download_metainfos(self, relpath, metainfos, url):
        relurls = []

        for metainfo in metainfos:
            js = metainfo.pop('download')

            reobj = re.search(r'javascript:openwin\("(?P<href>[^\"]+)"\)', js)
            if reobj is None:
                self.logger.warning('Unable to get gazette url from url %s', js)
                continue

            g = reobj.groupdict()

            href  = g['href']
            fname = href.split('/')[-1]

            reobj = re.search(r'\d+-\d+-\d+-(?P<part>\w+).pdf', fname)
            if reobj is None:
                self.logger.warning('Unable to get part number from url %s', href)
                continue

            g = reobj.groupdict()

            partnum = g['part']
            metainfo['partnum'] = partnum

            if metainfo['subject'].startswith('Extraordinary'):
                metainfo.set_gztype('Extraordinary')
            else:
                metainfo.set_gztype('Ordinary')
            metainfo.pop('subject')
            gzurl = urllib.parse.urljoin(url, href)
            relurl = os.path.join(relpath, partnum.lower())

            if self.save_gazette(relurl, gzurl, metainfo):
                relurls.append(relurl)

        return relurls

    def download_oneday(self, relpath, dateobj):
        dls = []
        url = self.baseurl.format(dateobj.year, dateobj.month, dateobj.day)

        response = self.download_url(url)
        if response is None or response.webpage is None:
            self.logger.warning('Unable to get page %s for date %s', url, dateobj)
            return dls

        metainfos = self.parse_results(response.webpage, dateobj)
        
        relurls = self.download_metainfos(relpath, metainfos, url)
        dls.extend(relurls)
        return dls
    
class MeghalayaNew(BaseGazette):
    def __init__(self, name, storage):
        BaseGazette.__init__(self, name, storage)
        self.baseurl  = 'https://megpns.gov.in/gazette/gazette_{}.html'
        self.hostname = 'megpns.gov.in'

    def parse_results(self, webpage, dateobj):
        metainfos = []

        d = utils.parse_webpage(webpage, self.parser)
        if d is None:
            self.logger.warning('Unable to parse result page for %s', dateobj)
            return metainfos

        for link in d.find_all('a'):
            href = link.get('href')
            if href is None:
                continue

            if not href.lower().endswith('.pdf'):
                continue

            fname = href.split('/')[-1]
            reobj = re.match(r'(?P<day>\d{2})-(?P<month>\d{2})-(?P<year>\d{2})-(?P<part>\w+)\.pdf$', fname, re.IGNORECASE)
            if reobj is None:
                continue

            g = reobj.groupdict()
            try:
                filedate = datetime.date(2000 + int(g['year']), int(g['month']), int(g['day']))
            except ValueError:
                self.logger.warning('Invalid date in filename: %s', fname)
                continue

            if filedate != dateobj:
                continue

            metainfo = utils.MetaInfo()
            metainfo.set_date(dateobj)
            metainfo['download'] = href
            metainfos.append(metainfo)

        return metainfos

    def download_metainfos(self, relpath, metainfos, url):
        relurls = []

        for metainfo in metainfos:
            href  = metainfo.pop('download')
            fname = href.split('/')[-1]

            reobj = re.search(r'\d+-\d+-\d+-(?P<part>\w+)\.pdf', fname, re.IGNORECASE)
            if reobj is None:
                self.logger.warning('Unable to get part number from url %s', href)
                continue

            g = reobj.groupdict()

            partnum = g['part']
            metainfo['partnum'] = partnum

            if partnum.upper() == 'X':
                metainfo.set_gztype('Extraordinary')
            else:
                metainfo.set_gztype('Ordinary')

            gzurl  = urllib.parse.urljoin(url, href)
            relurl = os.path.join(relpath, partnum.lower())

            if self.save_gazette(relurl, gzurl, metainfo):
                relurls.append(relurl)

        return relurls

    def download_oneday(self, relpath, dateobj):
        dls = []
        url = self.baseurl.format(dateobj.year)

        response = self.download_url(url, legacy_ssl_context = True)
        if response is None or response.webpage is None:
            self.logger.warning('Unable to get page %s for date %s', url, dateobj)
            return dls

        metainfos = self.parse_results(response.webpage, dateobj)

        relurls = self.download_metainfos(relpath, metainfos, url)
        dls.extend(relurls)
        return dls
