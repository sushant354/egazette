import datetime
import re
import os
import urllib.request, urllib.parse, urllib.error

from .basegazette import BaseGazette
from ..utils import utils

class Kerala(BaseGazette):
    def __init__(self, name, storage):
        BaseGazette.__init__(self, name, storage)
        self.hostname = 'www.egazette.kerala.gov.in'
        self.latest_url = 'http://www.egazette.kerala.gov.in/'
        self.baseurl    = self.latest_url
        self.parser     = 'html.parser'
        self.start_date   = datetime.datetime(2007, 1, 1)

        self.year_href =  '/archive%d_iframe.htm'

    def sync(self, fromdate, todate, event):
        newdownloads = []
        while fromdate <= todate:
            if event.is_set():
                self.logger.warn('Exiting prematurely as timer event is set')
                break

            dateobj   = fromdate.date()
            lastdate  = datetime.datetime(fromdate.year, 12, 31)
            if todate < lastdate:
                lastdate = todate
            lastdate = lastdate.date()

            self.logger.info('Dates:  %s to %s', dateobj, lastdate)

            dls = self.download_dates(self.name, dateobj, lastdate)

            self.logger.info('Got %d gazettes between  %s and %s' % (len(dls), dateobj, lastdate))
            newdownloads.extend(dls)
            fromdate = datetime.datetime(fromdate.year + 1, 1, 1)

        return newdownloads

    def download_dates(self, relpath, fromdate, todate):
        year = fromdate.year
        assert year == todate.year
        
        dls = []

        if year < 2007:
            self.logger.warn('Sorry no data for the year %s', year)
            return dls

        href = self.year_href % year
                
        urls = [urllib.parse.urljoin(self.baseurl, href)]
        if year == datetime.date.today().year:
            urls.append(self.latest_url)

        for url in urls:
            response = self.download_url(url)
            if not response or not response.webpage:
                self.logger.warn('Unable to download %s. Skipping %s to %s', url, fromdate, todate)
                continue
            d = utils.parse_webpage(response.webpage, self.parser)
            if not d:
                self.logger.warn('Unable to parse %s. Skipping %s to %s', url, fromdate, todate)
                continue

            minfos = self.process_listing_page(url, d, fromdate, todate)
            for metainfo in minfos:     
                relurl = self.get_relurl(metainfo)
                dateobj = metainfo.get_date()
                if not relurl or not dateobj:
                    self.logger.warn('Skipping. Could not get relurl/date for %s', metainfo)
                    continue

                relurl = os.path.join(relpath, dateobj.__str__(), relurl)
                gurl   = metainfo['url']

                if self.save_gazette(relurl, gurl, metainfo):
                    dls.append(relurl)
        return dls

    def get_relurl(self, metainfo):
        gurl  = metainfo['url']
        words = gurl.split('/')
        if len(words) == 0:
            return None

        filename = '.'.join(words[-1].split('.')[:-1])
        wordlist = [filename]

        pathwords = words[:-1]
        pathwords.reverse()

        i = 0
        for word in pathwords: 
            wordlist.append(word)
            if word.startswith('part') or i >= 3:
                break
            i += 1
        wordlist.reverse()
            
        relurl = '_'.join(wordlist)
        relurl, n = re.subn('[.\s-]+', '-', relurl)
        return relurl

    def process_listing_page(self, baseurl, d, fromdate, todate):
        minfos = []
        for link in d.find_all('a'):
            txt = utils.get_tag_contents(link)
            if not txt:
                continue

            dateobj = utils.get_date_from_title(txt)
            if not dateobj:
                self.logger.warn('Unable to extract date from %s', txt)
                continue

            if dateobj < fromdate or dateobj > todate:
                continue

            href = link.get('href')
            if not href:
                continue

            url = urllib.parse.urljoin(baseurl, href)
            minfos.extend(self.datepage_metainfos(url, dateobj))       
        return minfos

    def datepage_metainfos(self, url, dateobj):
        minfos = []
        response = self.download_url(url)

        if not response or not response.webpage:
            self.logger.warn('Unable to download %s. Skipping', url)
            return minfos

        d = utils.parse_webpage(response.webpage, self.parser)
        if not d:
            self.logger.warn('Unable to parse %s. Skipping.', url)
            return minfos

        partnum = None
        dept    = None
        for td in d.find_all('td'):
            bgcolor = td.get('bgcolor')
            links   = td.find_all('a')
            if bgcolor == '#91BAE8' and len(links) == 0:
                partnum =  utils.get_tag_contents(td)
                partnum  = utils.remove_spaces(partnum)
                dept    = None
            elif len(links) > 0:
                reobj  = re.compile('^(strong|a)$')
                for x in td.find_all(reobj):
                    if x.name == 'strong':
                        dept = utils.get_tag_contents(x)
                        dept = utils.remove_spaces(dept)
                    elif x.name == 'a'  and partnum:
                        href  = x.get('href')
                        if not href.startswith('pdf'):
                            continue

                        title = utils.get_tag_contents(x)
                        title = utils.remove_spaces(title)

                        metainfo = utils.MetaInfo()
                        minfos.append(metainfo)

                        metainfo.set_title(title)
                        metainfo.set_date(dateobj)     
                        metainfo['partnum'] = partnum
                        if dept:
                            metainfo['department']    = dept
                        gzurl = urllib.parse.urljoin(url, href)
                        metainfo['url'] = gzurl

        return minfos    
