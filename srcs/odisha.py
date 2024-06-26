import re
import os
import urllib.request, urllib.parse, urllib.error
from datetime import datetime

from ..utils import utils
from .basegazette import BaseGazette

class Odisha(BaseGazette):
    def __init__(self, name, storage):
        BaseGazette.__init__(self, name, storage)
        self.ordinary_url = 'https://ogpress.nic.in/odishagazettes.php'
        self.extraordinary_url = 'https://ogpress.nic.in/ex_odishagazettes.php'
        self.hostname = 'ogpress.nic.in'

    def find_field_order(self, tr, header_type):
        order = []
        for td in tr.find_all(header_type):
            txt = utils.get_tag_contents(td)
            if txt and re.search('Gazette\s+Number', txt):
                order.append('gznum')
            elif txt and re.search('Department', txt):
                order.append('department')
            elif txt and re.search('Gazette\s+Date', txt):
                order.append('gzdate')
            elif txt and re.search('Action', txt):
                order.append('download')
            elif txt and re.search('File', txt):
                order.append('file')
            else:
                order.append('')

        for field in ['download', 'gznum', 'gzdate']:
            if field not in order:
                return None
        return order

    def process_result_row(self, tr, dateobj, gztype, datefmt, order):
        metainfo = utils.MetaInfo()
        metainfo.set_gztype(gztype)
        metainfo.set_date(dateobj)
        gzdate = None
        filename = None
        i = 0
        for td in tr.find_all('td'):
            if len(order) > i:
                col = order[i]
                txt = utils.get_tag_contents(td)
                if txt:
                    txt = txt.strip()
                if col in ['gznum', 'department']:
                    metainfo[col] = txt
                elif col == 'gzdate':
                    gzdate = txt
                elif col == 'file':
                    filename = txt
                elif col == 'download':
                    link = td.find('a')
                    if link and link.get('href'):
                        metainfo['href'] =  link.get('href')    
            i += 1

        if gztype == 'Weekly':
            if filename == None or not filename.endswith('.pdf'):
                return None

        try:
            gzdateobj = datetime.strptime(gzdate, datefmt).date()
        except ValueError:
            #self.logger.warning('encountered unparsable date %s', gzdate)
            return None
        if gzdateobj != dateobj:
            return None
        return metainfo

    def download_onetype(self, relpath, dateobj, srcurl, gztype, datefmt, header_type):
        dls = []

        response = self.download_url(srcurl)
        if not response or not response.webpage:
            self.logger.warning('Unable to get result page for type %s for date %s', gztype, dateobj)
            return dls

        d = utils.parse_webpage(response.webpage, self.parser)
        if not d:     
            self.logger.warning('Unable to parse result page for type %s date %s', gztype, dateobj)
            return dls

        result_table = None
            
        for table in d.find_all('table'):
            for tr in table.find_all('tr'):
                order = self.find_field_order(tr, header_type)
                if order:
                    result_table = table
                    break
                 
        if result_table == None:
            self.logger.warning('Unable to find the result table for type %s date %s', gztype, dateobj)
            return dls

        minfos = []
        for tr in result_table.find_all('tr'):
            if tr.find('a') == None:
                continue
            metainfo = self.process_result_row(tr, dateobj, gztype, datefmt, order)
            if metainfo:
                minfos.append(metainfo)

        for metainfo in minfos:
            href   = metainfo.pop('href')
            url    = urllib.parse.urljoin(srcurl, href)
            relurl = os.path.join(relpath, metainfo['gznum'])
            if self.save_gazette(relurl, url, metainfo, validurl = False):
                dls.append(relurl)

        return dls


    def download_oneday(self, relpath, dateobj):
        odls = self.download_onetype(relpath, dateobj, self.ordinary_url, 'Weekly', '%Y-%m-%d', 'td')
        edls = self.download_onetype(relpath, dateobj, self.extraordinary_url, 'ExtraOrdinary', '%d-%m-%Y', 'th')
        return odls + edls
