import urllib.request
import urllib.parse
import urllib.error
import re
import os

from .basegazette import BaseGazette
from ..utils import utils

class Goa(BaseGazette):
    def __init__(self, name, storage):
        BaseGazette.__init__(self, name, storage)
        self.hostname = 'goaprintingpress.gov.in'
        self.searchurl = 'https://goaprintingpress.gov.in/search-e-gazettes-by-date/?'\
                         'task=search_by_date&Itemid=177&type=ALL&series=ALL&sdate={0}&edate={0}&action=search'

    def download_gazette(self, metainfo, searchurl, relpath):
        link = metainfo.pop('download')
        href = link.get('href')
        txt  = utils.get_tag_contents(link)
        txt = txt.strip()

        if not href or not txt:
            return None

        # remove extension in txt
        txt = '.'.join(txt.split('.')[:-1])
        relurl = os.path.join(relpath, txt)

        gzurl = urllib.parse.urljoin(searchurl, href)
        if not self.save_gazette(relurl, gzurl, metainfo):
            return None

        return relurl

    def download_metainfos(self, relpath, metainfos, searchurl):
        dls = []
        for metainfo in metainfos:
           relurl = self.download_gazette(metainfo, searchurl, relpath)
           if relurl:
                dls.append(relurl)
        return dls

    def get_field_order(self, tr):
        order = []
        for th in tr.find_all('th'):
            txt = utils.get_tag_contents(th)
            txt = txt.strip()
            if re.search(r'Gazette\s+No', txt):
                order.append('gznum')
            elif re.search('Series', txt):
                order.append('series')
            elif re.search('Type', txt):
                order.append('gztype')
            elif re.match(r'Reference\s+No', txt):
                order.append('num')
            elif re.search('Document', txt):
                order.append('download')
            else:
                order.append('')
        return order        

    def get_metainfo(self, order, tr, dateobj):
        metainfo = utils.MetaInfo()
        metainfo.set_date(dateobj)

        i = 0
        for td in tr.find_all('td'):
            txt = utils.get_tag_contents(td)
            txt = txt.strip()
            if order[i] == 'download':
                link = td.find('a')
                if link:
                    metainfo['download'] = link
            elif order[i] == 'gznum':
                metainfo['gznum'] = txt
            elif order[i] == 'gztype':
                metainfo.set_gztype(txt)
            elif order[i] == 'num':
                metainfo['num'] = txt
            elif order[i] == 'series':
                metainfo['series'] = txt
                    
            i += 1

        return metainfo

    def parse_search_results(self, webpage, dateobj, curr_page):
        metainfos = []
        nextpage  = None

        d = utils.parse_webpage(webpage, self.parser)
        if not d:
            self.logger.warning('Unable to parse search result page for %s', \
                                dateobj)
            return metainfos, nextpage

        tables = d.find_all('table', {'class': 'govt-gazette-table'})

        if len(tables) != 1:
            self.logger.warning('Could not find the result table for %s', \
                                dateobj)
            return metainfos, nextpage
        
        order = None
        for tr in tables[0].find_all('tr'):
            if not order:
                order = self.get_field_order(tr)
                continue

            metainfo = self.get_metainfo(order, tr, dateobj)
            if metainfo and 'download' in metainfo:
                metainfos.append(metainfo)

        pager_div = d.find('div', {'class': 'govt-pagination'})
        if pager_div is not None:
            nextpage = utils.find_next_page(d, curr_page)

        return metainfos, nextpage

    def download_oneday(self, relpath, dateobj):
        dls = []

        datestr   = dateobj.strftime('%d-%m-%Y')
        searchurl = self.searchurl.format(datestr)

        response = self.download_url(searchurl)

        pagenum = 1
        while response is not None and response.webpage is not None:
            curr_url = response.response_url

            metainfos, nextpage = self.parse_search_results(response.webpage, \
                                                            dateobj, pagenum)

            relurls = self.download_metainfos(relpath, metainfos, curr_url)

            dls.extend(relurls)

            if not nextpage:
                break

            pagenum += 1
            self.logger.info('Going to page %d for date %s', pagenum, dateobj)

            nexturl  = urllib.parse.urljoin(searchurl, nextpage['href'])
            response = self.download_url(nexturl)
 
        return dls


