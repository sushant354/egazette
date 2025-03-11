import urllib.request, urllib.parse, urllib.error
import re
import os

from .basegazette import BaseGazette
from ..utils import utils

class Goa(BaseGazette):
    def __init__(self, name, storage):
        BaseGazette.__init__(self, name, storage)
        self.hostname = 'goaprintingpress.gov.in'
        self.searchurl = 'https://goaprintingpress.gov.in/search-by-date/?task=search_by_date&Itemid=177&type=ALL&series=ALL&sdate=%s&edate=%s&action=search'

    def download_oneday(self, relpath, dateobj):
        dls = []
        datestr = utils.dateobj_to_str(dateobj, '-')
        searchurl = self.searchurl % (datestr, datestr)
        response = self.download_url(searchurl)
        if not response or not response.webpage:
            self.logger.warning('Could not download search result for date %s', \
                              dateobj)
            return dls

        d = utils.parse_webpage(response.webpage, self.parser)
        if not d:
            self.logger.warning('Could not parse search result for date %s', \
                              dateobj)
            return dls

        minfos = self.parse_results(d, dateobj)
        for metainfo in minfos:
            if 'download' not in metainfo:
                self.logger.warning('No link. Ignoring metainfo: %s', metainfo)
                continue
            relurl = self.download_gazette(metainfo, searchurl, relpath)
            if relurl:
                dls.append(relurl)
        return dls

    def download_gazette(self, metainfo, searchurl, relpath):
        link = metainfo.pop('download')
        href = link.get('href')
        txt  = utils.get_tag_contents(link)
        txt = txt.strip()

        if not href or not txt:
            return None
        txt = '.'.join(txt.split('.')[:-1])
        relurl = os.path.join(relpath, txt)
        gzurl  = urllib.parse.urljoin(searchurl, href)
        if self.save_gazette(relurl, gzurl, metainfo):
            return relurl
        return None    
       
    def get_field_order(self, tr):
        order = []
        for td in tr.find_all('td'):
            txt = utils.get_tag_contents(td)
            txt = txt.strip()
            if re.search('Gazette\s+No', txt):
                order.append('gznum')
            elif re.search('Series', txt):
                order.append('series')
            elif re.search('Type', txt):
                order.append('gztype')
            elif re.match('No', txt):
                order.append('num')
            elif re.search('Download', txt):
                order.append('download')
            else:
                order.append('')
        return order        

    def parse_results(self, d, dateobj):
        minfos = []
        result_table = d.find('table', {'class': 'gazettes'})

        if result_table == None:
            self.logger.warning('Did not get the result table for %s', dateobj)
            return minfos

        order = None
        for tr in result_table.find_all('tr'):
            if not order:
                order = self.get_field_order(tr)
                continue
            
            metainfo = self.get_metainfo(order, tr, dateobj)
            if metainfo and 'download' in metainfo:
                minfos.append(metainfo)
        return minfos

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


