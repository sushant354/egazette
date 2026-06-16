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
        self.baseurl  = 'https://megpns.gov.in/gazette/gazette.html'
        self.hostname = 'megpns.gov.in'

    def get_year_urls(self, webpage):
        d = utils.parse_webpage(webpage, self.parser)
        if d is None:
            return {}

        year_urls = {}
        for a in d.find_all('a', href=True):
            href = a.get('href', '')
            m = re.match(r'gazette_(\d{4})\.html$', href)
            if m:
                year = int(m.group(1))
                year_urls[year] = urllib.parse.urljoin(self.baseurl, href)
        return year_urls

    def parse_year_page(self, webpage, year_page_url):
        metainfos = []

        d = utils.parse_webpage(webpage, self.parser)
        if d is None:
            return metainfos

        base = year_page_url.rsplit('/', 1)[0] + '/'

        for a in d.find_all('a', href=True):
            href = a.get('href', '')
            if not href.lower().endswith('.pdf'):
                continue

            fname = href.split('/')[-1]
            m = re.match(r'(\d{2})-(\d{2})-(\d{2})-(\w+)\.pdf$', fname, re.IGNORECASE)
            if not m:
                continue

            day, month, yy, part = int(m.group(1)), int(m.group(2)), int(m.group(3)), m.group(4)
            full_year = 2000 + yy

            try:
                dateobj = datetime.date(full_year, month, day)
            except ValueError:
                self.logger.warning('Invalid date in filename: %s', fname)
                continue

            metainfo = utils.MetaInfo()
            metainfo.set_date(dateobj)
            metainfo['partnum'] = part
            metainfo['download_url'] = urllib.parse.urljoin(base, href)

            if part.upper() == 'X':
                metainfo.set_gztype('Extraordinary')
            else:
                metainfo.set_gztype('Ordinary')

            metainfos.append(metainfo)

        return metainfos

    def download_metainfos(self, metainfos, fromdate, todate):
        relurls = []

        for metainfo in metainfos:
            dateobj = metainfo.get_date()
            if dateobj < fromdate or dateobj > todate:
                continue

            gzurl = metainfo.pop('download_url')
            part  = metainfo['partnum']

            relpath = os.path.join(self.name, dateobj.__str__())
            relurl  = os.path.join(relpath, part.lower())

            if self.save_gazette(relurl, gzurl, metainfo):
                relurls.append(relurl)

        return relurls

    def sync(self, fromdate, todate, event):
        dls      = []
        fromdate = fromdate.date()
        todate   = todate.date()

        response = self.download_url(self.baseurl)
        if not response or not response.webpage:
            self.logger.warning('Unable to fetch main gazette page %s', self.baseurl)
            return dls

        year_urls = self.get_year_urls(response.webpage)
        self.logger.info('Found year pages: %s', sorted(year_urls.keys()))

        for year in range(fromdate.year, todate.year + 1):
            if event.is_set():
                self.logger.warning('Exiting prematurely as timer event is set')
                break

            year_url = year_urls.get(year)
            if not year_url:
                self.logger.warning('No gazette page found for year %d', year)
                continue

            self.logger.info('Fetching gazette list for year %d from %s', year, year_url)
            response = self.download_url(year_url)
            if not response or not response.webpage:
                self.logger.warning('Unable to fetch year page for %d', year)
                continue

            metainfos = self.parse_year_page(response.webpage, year_url)
            self.logger.info('Found %d gazette entries for %d', len(metainfos), year)

            relurls = self.download_metainfos(metainfos, fromdate, todate)
            self.logger.info('Downloaded %d gazettes for %d', len(relurls), year)
            dls.extend(relurls)

        self.logger.info('Got %d gazettes from %s to %s', len(dls), fromdate, todate)
        return dls
