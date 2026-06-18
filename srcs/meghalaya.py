import re
import os
import urllib.parse

from ..utils import utils
from .basegazette import BaseGazette
import datetime

class Meghalaya(BaseGazette):
    def __init__(self, name, storage):
        BaseGazette.__init__(self, name, storage)
        self.baseurl  = 'https://megpns.gov.in/gazette/gazette_{}.html'
        self.hostname = 'megpns.gov.in'

    def parse_index(self, webpage):
        """Parse the year index page and return list of (dateobj, href) for all available PDFs."""
        results = []
        d = utils.parse_webpage(webpage, self.parser)
        if d is None:
            self.logger.warning('Unable to parse index page')
            return results

        for link in d.find_all('a'):
            href = link.get('href')
            if href is None or not href.lower().endswith('.pdf'):
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

            results.append((filedate, href))

        return results

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
            relurl = os.path.join(relpath, os.path.splitext(fname)[0])

            if self.save_gazette(relurl, gzurl, metainfo):
                relurls.append(relurl)

        return relurls

    def sync(self, fromdate, todate, event):
        newdownloads = []

        # Fetch each year's index page once and collect available dated PDFs
        date_to_entries = {}  # dateobj -> (page_url, [href, ...])
        for year in range(fromdate.year, todate.year + 1):
            url = self.baseurl.format(year)
            response = self.download_url(url, legacy_ssl_context=True)
            if response is None or response.webpage is None:
                self.logger.warning('Unable to get index page %s', url)
                continue

            for filedate, href in self.parse_index(response.webpage):
                if fromdate.date() <= filedate <= todate.date():
                    entry = date_to_entries.setdefault(filedate, (url, []))
                    entry[1].append(href)

        for dateobj in sorted(date_to_entries.keys()):
            if event.is_set():
                self.logger.warning('Exiting prematurely as timer event is set')
                break

            page_url, hrefs = date_to_entries[dateobj]
            tmprel = os.path.join(self.name, dateobj.__str__())

            metainfos = []
            for href in hrefs:
                metainfo = utils.MetaInfo()
                metainfo.set_date(dateobj)
                metainfo['download'] = href
                metainfos.append(metainfo)

            relurls = self.download_metainfos(tmprel, metainfos, page_url)
            self.logger.info('Got %d gazettes for day %s', len(relurls), dateobj)
            newdownloads.extend(relurls)

        return newdownloads
