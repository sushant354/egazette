import datetime
import os
import re
import urllib.request
import urllib.parse
import urllib.error

from .basegazette import BaseGazette
from ..utils import utils


class Nagaland(BaseGazette):
    def __init__(self, name, storage):
        BaseGazette.__init__(self, name, storage)
        self.hostname = 'govtpress.nagaland.gov.in'
        self.baseurl_new = 'https://govtpress.nagaland.gov.in/egazette-latest/'
        self.baseurl_old = 'https://govtpress.nagaland.gov.in'

    def get_metainfos_from_page(self, webpage):
        d = utils.parse_webpage(webpage, self.parser)
        if d is None:
            self.logger.warning('Unable to parse webpage for metainfos')
            return None

        metainfos = []
        for article in d.find_all('article'):
            if article.find('article') is not None:
                continue

            link = article.find('a')
            if link is None:
                self.logger.warning('Unable to locate link in article')
                continue

            href = link.get('href')
            if href is None:
                continue

            title = utils.get_tag_contents(link)
            reobj = re.search(r'egazette\s+(?P<day>\d+)\s+(?P<month>\w+)\s+(?P<year>\d+)', title, re.IGNORECASE)
            if not reobj:
                self.logger.warning('Unable to match date string in title %s', title)
                continue

            g = reobj.groupdict()
            try:
                issuedate = datetime.datetime.strptime('%s-%s-%s' % (g['day'], g['month'][:3], g['year']), '%d-%b-%Y').date()
            except ValueError:
                self.logger.warning('Unable to get date from %s', title)
                continue

            metainfo = utils.MetaInfo()
            metainfo.set_date(issuedate)
            metainfo['href'] = href
            metainfos.append(metainfo)

        return metainfos

    def download_metainfos(self, metainfos, dls, event, fromdate, todate):
        for metainfo in metainfos:
            if event.is_set():
                self.logger.warning('Exiting prematurely as timer event is set')
                return dls

            metadate = metainfo.get_date()
            if fromdate.date() <= metadate <= todate.date():
                page_url = metainfo.pop('href')
                response = self.download_url(page_url)
                if response is None or response.webpage is None:
                    self.logger.warning('Unable to get page %s for date %s', page_url, metadate)
                    continue

                curr_url = response.response_url

                d = utils.parse_webpage(response.webpage, self.parser)
                if d is None:
                    continue

                obj = d.find('object')
                if not obj:
                    self.logger.warning('No object found in %s', page_url)
                    continue

                gzurl = obj.get('data')
                if not gzurl:
                    self.logger.warning('No href found for link in object in %s', page_url)
                    continue

                gzurl = urllib.parse.urljoin(curr_url, gzurl)
                relpath = os.path.join(self.name, metadate.__str__()) 
                relurl = os.path.join(relpath, 'gazette')
                if self.save_gazette(relurl, gzurl, metainfo):
                    dls.append(relurl)

    def get_metainfos(self, webpage, year):
        d = utils.parse_webpage(webpage, self.parser)
        if d is None:
            return None

        article = d.find('article')
        if article is None:
            return None

        items = []
        if year == 2017:
            for li in article.find_all('li'):
                link = li.find('a')
                if link is None:
                    continue

                href = link.get('href')
                if href is None:
                    continue

                txt = utils.get_tag_contents(link)

                items.append((txt, href))
        else:
            table = article.find('table')
            if table is None:
                return None

            for tr in table.find_all('tr'):
                if tr.find('a') is None:
                    continue

                tds = tr.find_all('td')
                if len(tds) != 2:
                    continue

                txt = utils.get_tag_contents(tds[1])

                link = tds[0].find('a')
                if link is None:
                    continue

                href = link.get('href')

                if href is not None and href.endswith('.pdf'):
                    items.append((txt, href))

        metainfos = []
        for txt, url in items:
            txt = txt.strip()

            if txt.startswith('Gazette'):
                txt = txt[len('Gazette'):]
                txt = txt.strip()

            reobj = re.search(r'(?P<day>\d+)\s*(th|st|nd)?\s*(th|st|nd)?\s*(?P<month>[a-zA-Z]+)\s*(,)?\s*(?P<year>\d+)', txt)
            if reobj is None:
                reobj = re.search(r'(?P<month>[a-zA-Z]+)\s*(?P<day>\d+)\s*(th|st)?\s*(,)?\s*(?P<year>\d+)', txt)
            if reobj is None:
                self.logger.warning('Unable to match date string for %s', txt)
                continue

            g = reobj.groupdict()

            g['month'] = g['month'][:3]

            issuedate  = datetime.datetime.strptime(f'{g["day"]}-{g["month"]}-{g["year"]}', '%d-%b-%Y').date()

            metainfo = utils.MetaInfo()
            metainfo.set_date(issuedate)
            metainfo['download'] = url

            metainfos.append(metainfo)

        return metainfos

    def sync(self, fromdate, todate, event):
        newdls = []
 
        
        fromyear = fromdate.year
        toyear   = todate.year

        for year in range(fromyear, toyear+1):
            dls = []
            year_href = 'egazette-%s/' % year
            year_url = urllib.parse.urljoin(self.baseurl_old, year_href)
 
            response = self.download_url(year_url)
            if response is None or response.webpage is None:
                self.logger.warning('Unable to get %s for year %d', year_url, year)
                continue
 
            metainfos = self.get_metainfos(response.webpage, year)
            if metainfos is None:
                self.logger.warning('Unable to parse year page at %s for year %s', year_url, year)
                continue

            for metainfo in metainfos:
                if event.is_set():
                    self.logger.warning('Exiting prematurely as timer event is set')
                    return dls

                metadate = metainfo.get_date()

                if fromdate.date() <= metadate <= todate.date():
                    gzurl = metainfo.pop('download')

                    file_name = os.path.basename(gzurl)
                    file_name = os.path.splitext(file_name)[0]
                    relpath = os.path.join(self.name, metadate.__str__()) 
                    relurl  = os.path.join(relpath, file_name)
                    gzurl = urllib.parse.urljoin(year_url, gzurl)

                    if self.save_gazette(relurl, gzurl, metainfo):
                        dls.append(relurl)

            self.logger.info('Got %d gazettes for year %s.' % (len(dls), year))
            newdls.extend(dls)
        return newdls

