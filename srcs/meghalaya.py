import re
import os
import urllib.parse

from ..utils import utils
from .basegazette import BaseGazette

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