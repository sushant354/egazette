import datetime
import re
import os
import urllib.request, urllib.parse, urllib.error

from .basegazette import BaseGazette
from ..utils import utils
from ..utils.metainfo import MetaInfo

class MadhyaPradesh(BaseGazette):
    def __init__(self, name, storage):
        BaseGazette.__init__(self, name, storage)
        self.baseurl  = 'https://govtpressmp.nic.in/gazette.html'
        self.hostname = 'govtpressmp.nic.in'

        self.extraordinary_url =  '/history-gazette-extra-%d.html'
        self.ordinary_urls = {\
            ('Part 1', '/history-gazette-1-%d.html'), \
            ('Part 2', '/history-gazette-2-%d.html'), \
            ('Part 3', '/history-gazette-3-%d.html'), \
            ('Part 4', '/history-gazette-4-%d.html'), \
        }

    def download_oneday(self, relpath, dateobj):
        dls = []

        self.download_extraordinary(dls, relpath, dateobj)
        self.download_ordinary(dls, relpath, dateobj)

        return dls
    
    def download_ordinary(self, dls, relpath, dateobj):
        for partnum, parturl in self.ordinary_urls:    
            parturl = urllib.parse.urljoin(self.baseurl, parturl % dateobj.year)
            response = self.download_url(parturl)
            if not response or not response.webpage:
                self.logger.warning('Unable to download Ordinary gazette list for Part %s, year %d', partnum, dateobj.year)
                continue

            d = utils.parse_webpage(response.webpage, self.parser)
            if not d:    
                self.logger.warning('Unable to parse Ordinary gazette list for Part %s, year %d', partnum, dateobj.year)
                continue
            
            minfos = self.parse_listing_webpage(parturl, d, dateobj, partnum, 'Ordinary')
            self.download_metainfos(minfos, dls, relpath)

    def download_extraordinary(self, dls, relpath, dateobj):
        ex_url = urllib.parse.urljoin(self.baseurl, self.extraordinary_url % dateobj.year)

        response = self.download_url(ex_url)
        if not response or not response.webpage:
            self.logger.warning('Unable to download Extraordinary gazette for year %d', dateobj.year)
            return

        d = utils.parse_webpage(response.webpage, self.parser)
        if not d:    
            self.logger.warning('Unable to parse Extraordinary gazette list for year %d', dateobj.year)
            return
            
        if dateobj.year == 2010:
            minfos = self.parse_listing_webpage(ex_url, d, dateobj, None, 'Extraordinary')
        else:    
            minfos = self.parse_extraordinary_webpage(d, dateobj, ex_url)

        self.download_metainfos(minfos, dls, relpath)

    def parse_listing_webpage(self, parturl, d, dateobj, partnum, gztype):
        minfos = []
        for li in d.find_all('li'):
            link = li.find('a')
            if link == None:
                continue

            href = link.get('href')
            if href and href.startswith('pdf'):
                url = urllib.parse.urljoin(parturl, href)
                txt = utils.get_tag_contents(li)
                txt = txt.strip()
                if not txt:
                    continue

                nums = re.findall('\d+', txt)
                if len(nums) < 4:
                    self.logger.warning('Not able to parse. Ignoring %s', link)
                    continue

                gznum = ''.join(nums[:-3])
                try:
                    date  = datetime.date(int(nums[-1]), int(nums[-2]), int(nums[-3]))    
                except:
                    self.logger.warning('Could not get date. Ignoring %s', txt)
                    continue
                
                if date != dateobj:
                    continue
                                
                metainfo = MetaInfo()
                metainfo.set_gztype(gztype)
                metainfo.set_date(dateobj)
                metainfo.set_url(url)
                metainfo['gznum']   = gznum
                if partnum:
                    metainfo['partnum'] = partnum

                minfos.append(metainfo)

        return minfos

    def find_result_table(self, d):        
        tables = d.find_all('table')
        
        tablelist = []
        for table in tables:
            if table.find('table') == None:
                tablelist.append((table, len(table.find_all('tr'))))

        tablelist.sort(key = lambda x: x[1], reverse = True)
        if not tablelist:        
            return None

        return tablelist[0][0]
            
    def parse_extraordinary_webpage(self, d, dateobj, ex_url):
        minfos = []

        result_table = self.find_result_table(d)
        if result_table == None:
            self.loger.warning('Could not find result table for date %s', dateobj)
            return minfos

        order = None
        for tr in result_table.find_all('tr'):
            if not order:
                order = self.find_result_order(tr)
                continue
            
            link = tr.find('a')
            if link == None:
                continue

            metainfo = self.process_row(tr, order, dateobj)
            if metainfo:
                href = link.get('href')
                if href:
                    gzurl = urllib.parse.urljoin(ex_url, href)
                    metainfo.set_url(gzurl)
                    minfos.append(metainfo)

        return minfos                    
    
    def find_result_order(self, tr):
        order = []
        for td in tr.find_all('th'):
            txt = utils.get_tag_contents(td)
            if txt and re.search('\u0935\u093f\u0937\u092f', txt):
                order.append('subject')
            elif txt and re.search('\u0935\u093f\u092d\u093e\u0917', txt):
                order.append('department')
            elif txt and re.search('\u0926\u093f\u0928\u093e\u0902\u0915', txt):
                order.append('date')
            elif txt and re.search('\u0915\u094d\u0930\.', txt):
                order.append('gznum')
            else:
                order.append('')

        if 'subject' in order and 'date' in order and 'gznum' in order:
            return order

        return None     
    
    def process_row(self, tr, order, dateobj):    
        metainfo = MetaInfo()
        i = 0
        for td in tr.find_all('td'):
            txt = utils.get_tag_contents(td)
            if txt and order[i] in ['subject', 'department', 'gznum']:
                txt, n = re.subn('\s+', ' ', txt)
                metainfo[order[i]] = txt.strip()
            elif txt and order[i] == 'date':
                nums = re.split('[./-]+', txt)
                if len(nums) < 3:
                    self.logger.warning('Couldn\'t get date from %s for extraordinary gazette list', txt)
                    i += 1
                    continue

                nums = [re.subn('\s+', '', n)[0] for n in nums]
                nums = [n for n in nums if n]
                d = datetime.date(int(nums[2]), int(nums[1]), int(nums[0]))
                try:
                    metainfo.set_date(d)
                except:
                    self.logger.warning('Could not parse date %s', txt)
                    
            i += 1
        if metainfo.get_date() == dateobj:
            metainfo.set_gztype('Extraordinary')
            return metainfo

        return None    

    def download_metainfos(self, minfos, dls, relpath):
        for metainfo in minfos:
            if not 'gztype' in metainfo or not 'gznum' in metainfo or \
                    not 'url' in metainfo:
                self.logger.warning('Ignoring as not enough info to download: %s', metainfo)
                continue

            filename = '%s_%s' % (metainfo['gztype'], metainfo['gznum'])
            if 'partnum' in metainfo:
                filename = '%s_%s' % (filename, metainfo['partnum'])    
            filename, n = re.subn('\s+', '-', filename)

            relurl   = os.path.join(relpath, filename)

            if self.save_gazette(relurl, metainfo['url'], metainfo):
                dls.append(relurl)
