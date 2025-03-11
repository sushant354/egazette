import re
import os
import urllib.request, urllib.parse, urllib.error
import datetime

from ..utils import utils
from .basegazette import BaseGazette
from ..utils.metainfo import MetaInfo

class Odisha(BaseGazette):
    def __init__(self, name, storage):
        BaseGazette.__init__(self, name, storage)
        self.baseurl = 'http://govtpress.odisha.gov.in/notdtsearch.asp'
        self.hostname = 'govtpress.odisha.gov.in'

    def get_post_data(self, dateobj):
        return [('bsubmit', 'Submit'), ('select', utils.pad_zero(dateobj.day)),\
                ('select2', utils.pad_zero(dateobj.month)), \
                ('select3', utils.pad_zero(dateobj.year % 2000))]

    def find_field_order(self, tr):
        order  = []
        for td in tr.find_all('td'):
            txt = utils.get_tag_contents(td)
            if txt and re.search('Department', txt):
                order.append('department')
            elif txt and re.search('Notification\s+Number', txt):
                order.append('notification_num')
            elif txt and re.search('Gazette\s+Number', txt):
                order.append('gznum')
            elif txt and re.search('Subject', txt):
                order.append('subject')
            elif txt and re.search('File', txt):
                order.append('download')
            elif txt and re.search('Gazette\s+Date', txt):
                order.append('gzdate')
            else:
                order.append('')    
        
        for field in ['department', 'download', 'subject', 'gznum', 'notification_num']:
            if field not in order:
                return None
        return order
                
    def process_row(self, tr, order, dateobj):
        metainfo = MetaInfo()
        metainfo.set_date(dateobj)
        i = 0
        for td in tr.find_all('td'):
            if len(order) > i:
                txt = utils.get_tag_contents(td)
                txt = txt.strip()
                if order[i] in ['gznum', 'department', 'notification_num', 'subject']:
                    metainfo[order[i]] = txt
                elif order[i] == 'gzdate':
                    nums = re.findall('\d+', txt)
                    if len(nums) == 3:
                        try:
                            d = datetime.date(int(nums[2]), int(nums[1]), int(nums[0]))
                            metainfo['gzdate'] = d
                        except:
                            self.logger.warning('Unable to form date for %s', txt)        
                elif order[i] == 'download':
                    link = td.find('a')
                    if link and link.get('href'):
                        metainfo['href'] =  link.get('href')    

            i += 1
        if 'href' in metainfo and 'gznum' in metainfo:
            return metainfo
        return None
                
    def download_oneday(self, relpath, dateobj):
        dls = []
        postdata = self.get_post_data(dateobj)
        response = self.download_url(self.baseurl, postdata = postdata) 
        if not response or not response.webpage:
            self.logger.warning('Unable to get result page for date %s', dateobj)
            return dls

        d = utils.parse_webpage(response.webpage, self.parser)
        if not d:     
            self.logger.warning('Unable to parse result page for date %s', dateobj)
            return dls

        result_table = None
            
        for table in d.find_all('table'):
            for tr in table.find_all('tr'):
                order = self.find_field_order(tr)
                if order:
                    result_table = table
                    break
                 
        if result_table == None:
            self.logger.warning('Unable to find the result table for %s', dateobj)
            return dls

        minfos = []
        for tr in result_table.find_all('tr'):
            if tr.find('a') == None:
                continue
            metainfo = self.process_row(tr, order, dateobj)
            if metainfo:
                minfos.append(metainfo)
        
                    
        for metainfo in minfos:
            href   = metainfo.pop('href')
            url    = urllib.parse.urljoin(self.baseurl, href)
            relurl = os.path.join(relpath, metainfo['gznum'])
            if self.save_gazette(relurl, url, metainfo):
                dls.append(relurl)

        return dls        
