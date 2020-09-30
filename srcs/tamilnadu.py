import datetime
import os
import re
import urllib.request, urllib.parse, urllib.error

from .basegazette import BaseGazette
from ..utils import utils
                
class TamilNadu(BaseGazette):
    def __init__(self, name, storage):
        BaseGazette.__init__(self, name, storage)
        self.hostname = 'www.stationeryprinting.tn.gov.in'
        self.baseurl  = 'http://www.stationeryprinting.tn.gov.in'

        self.ordinary_byyear = '/gazette/gazette_list%d.php'
        self.extraordinary_byyear = '/extraordinary/extraord_list%d.php'

        self.ordinary_latest      = '/gazette/gazette_list.php'
        self.extraordinary_latest = '/extraordinary/extraord_list.php'
        self.start_date           = datetime.datetime(2008, 1, 1)

    def download_oneday(self, relpath, dateobj):
        dls = []
        today = datetime.date.today()

        ordinary_url      = None
        extraordinary_url = None

        start_date = self.start_date.date()
        if today.year == dateobj.year:
            ordinary_url      = self.ordinary_latest
            extraordinary_url = self.extraordinary_latest
        elif dateobj >= start_date:
            ordinary_url      = self.ordinary_byyear % dateobj.year    
            extraordinary_url = self.extraordinary_byyear % dateobj.year    
        
        if ordinary_url:
            self.download_ordinary(ordinary_url, dls, relpath, dateobj)

        if extraordinary_url:
            self.download_extraordinary(extraordinary_url, dls, relpath, dateobj)
        return dls
            
    def download_ordinary(self, href, dls, relpath, dateobj):
         metainfos = self.get_metainfos(href, dateobj, \
                           self.ordinary_field_order, self.process_ordinary_row)

         self.process_metainfos(metainfos, dls, relpath)
                   
    def download_extraordinary(self, href, dls, relpath, dateobj):
        metainfos = self.get_metainfos(href, dateobj, \
                                       self.extraordinary_field_order, \
                                       self.process_extraordinary_row)

        self.process_metainfos(metainfos, dls, relpath)

    def process_metainfos(self, metainfos, dls, relpath):
        for metainfo in metainfos:
            if 'gztype' not in metainfo or 'gznum' not in metainfo or \
                    'url' not in metainfo:
                self.logger.warn('No gznum or gztype in metainfo. Ignoring %s', metainfo)
                continue

            filename = '%s_%s' % (metainfo['gztype'], metainfo['gznum'])
            if 'partnum' in metainfo:
                filename = '%s_%s' % (filename, metainfo['partnum'])
            if 'section' in metainfo:    
                filename = '%s_%s' % (filename, metainfo['section'])
            filename, n = re.subn('\s+', '-', filename)
                
            relurl = os.path.join(relpath, filename)
            if self.save_gazette(relurl, metainfo.get_url(), metainfo):
                dls.append(relurl)
    
    def get_result_table(self, url):
        response = self.download_url(url)
        if not response or not response.webpage:
            self.logger.info('Unable to ftech the webpage for url: %s',  url)
            return None 

        d = utils.parse_webpage(response.webpage, self.parser)    
        if not d:
            self.logger.info('Unable to parse the webpage for url: %s',  url)
            return None 

        tables = d.find_all('table')
        
        tablelist = []
        for table in tables:
            if table.find('table') == None:
                tablelist.append((table, len(table.find_all('tr'))))

        tablelist.sort(key = lambda x: x[1], reverse = True)
        if not tablelist:        
            return None

        return tablelist[0][0]
                
    def get_metainfos(self, href, dateobj, get_field_order, process_row):
        minfos = []
        url = urllib.parse.urljoin(self.baseurl, href)
        result_table = self.get_result_table(url)
        if result_table == None:
            self.logger.warn('Unable to get result table for year %d', dateobj.year)
            return minfos

        order = None
        for tr in result_table.find_all('tr'):
            if not order:
                order = get_field_order(tr)
                continue
            process_row(minfos, tr, order, dateobj, url)
        return minfos

    def ordinary_field_order(self, tr):
        order = []
        found = False
        for td in tr.find_all('td'):
            txt = utils.get_tag_contents(td)
            if txt and re.search('Issue\s+No', txt, re.IGNORECASE):
                order.append('gznum')
                found = True
            elif txt and re.search('Particulars', txt, re.IGNORECASE):
                order.append('subject')
                found = True
            else:
                order.append('')    
        if found:
            return order

        return None

    def process_ordinary_row(self, minfos, tr, order, dateobj, url):
        i = 0
        metainfo = utils.MetaInfo()
        
        for td in tr.find_all('td'):
            if i < len(order): 
                if order[i] == 'subject':
                    metainfo.set_subject([utils.get_tag_contents(li) for li in td.find_all('li')])
                elif order[i] == 'gznum':
                    link = td.find('a')
                    if link and link.get('href'):
                        href = link.get('href')
                        metainfo.set_url(urllib.parse.urljoin(url, href))

                    txt = utils.get_tag_contents(td)
                    reobj = re.search('(?P<gznum>\w+)[\s-]*dt[.\s-]*(?P<day>\d+)-(?P<month>\d+)-(?P<year>\d+)', txt)
                    if reobj:
                        groupdict = reobj.groupdict()
                        metainfo['gznum'] = groupdict['gznum']
                        try:
                            d = datetime.date(int(groupdict['year']), \
                                              int(groupdict['month']), \
                                              int(groupdict['day']))
                            metainfo.set_date(d)
                        except:
                            self.logger.warn('Unable to create date from %s', txt)
            
            i += 1

        url   =  metainfo.get_url()
        gznum = metainfo.get('gznum')

        if metainfo.get_date() == dateobj and url and gznum:
            self.process_ordinary_listing(minfos, url, gznum, dateobj) 

    def get_listing_order(self, tr):
        order = [] 
        found = False
        for td in tr.find_all('td'): 
            txt = utils.get_tag_contents(td)
            if txt and re.search('Click\s+to', txt):
                order.append('download')
                found = True
            elif txt and re.search('Content', txt):
                order.append('subject')
                found = True
            else:
                order.append('')
        if not found:
            self.logger.warn('No order for ordinary gazette listing: %s', tr)
            return None        

        return order            
                
    def process_ordinary_listing(self, minfos, url, gznum, dateobj):
        result_table = self.get_result_table(url)
        if result_table == None:
            self.logger.warn('Unable to fetch the ordinary gazette listing %s', url)
            return

        order = None
        for tr in result_table.find_all('tr'):
            if not order:
                order = self.get_listing_order(tr)
                continue    

            i = 0
            metainfo = utils.MetaInfo()
            metainfo.set_gztype('Ordinary')
            metainfo['gznum'] = gznum
            metainfo.set_date(dateobj)

            for td in tr.find_all('td'):
                if i < len(order):
                    if order[i] == 'subject':
                        lis = [li.extract() for li in td.find_all('li')]
                        notifications = [utils.get_tag_contents(li) for li in lis]
                        metainfo['notifications'] = notifications
                        txt = utils.get_tag_contents(td)
                        if txt:
                            metainfo['subject'] = txt

                    elif order[i] == 'download':
                        link = td.find('a')
                        if link and link.get('href'):
                            href = link.get('href')
                            metainfo.set_url(urllib.parse.urljoin(url, href))
                        txt = utils.get_tag_contents(td)
                        if txt:
                           reobj = re.search('Part\s+\w+', txt)     
                           if reobj:
                               metainfo['partnum'] = txt[reobj.start():reobj.end()]
                               if len(txt) > reobj.end():
                                   txt = txt[reobj.end():]
                                   txt = txt.strip(' -\t\r\n')
                                   if txt:
                                       metainfo['section'] = txt
                i += 1           
            if metainfo.get_url():
                minfos.append(metainfo)
                    
    def extraordinary_field_order(self, tr):
        order = []
        found = False
        for td in tr.find_all('td'):
            txt = utils.get_tag_contents(td)
            if txt and re.search('Issue\s+No', txt, re.IGNORECASE):
                order.append('gznum')
                found = True
            elif txt and re.search('Issue\s+Date', txt, re.IGNORECASE):
                order.append('date')
                found = True
            elif txt and re.search('Extraordinary\s+Part', txt, re.IGNORECASE):
                order.append('partnum')
                found = True
            elif txt and re.search('Extraordinary\s+Type', txt, re.IGNORECASE):
                order.append('extraordinary_type')
                found = True
            elif txt and re.search('Subject', txt, re.IGNORECASE):
                order.append('subject')
                found = True
            else:
                order.append('')    
        if found:
            return order

        return None

    def process_extraordinary_row(self, minfos, tr, order, dateobj, url):
        i = 0
        metainfo = utils.MetaInfo()
        for td in tr.find_all('td'):
            if i < len(order): 
                txt = utils.get_tag_contents(td)
                txt = txt.strip()
                if not txt:
                    i += 1
                    continue

                if order[i] == 'gznum':
                    link = td.find('a')
                    if link and link.get('href'):
                        href = link.get('href')
                        metainfo.set_url(urllib.parse.urljoin(url, href))

                    if txt:
                        metainfo['gznum'] = txt
                elif order[i] == 'date':
                    ds = re.findall('\d+', txt)
                    if len(ds) == 3:
                        try:
                            d = datetime.date(int(ds[2]), int(ds[1]), int(ds[0]))
                            metainfo.set_date(d)
                        except:    
                            self.logger.warn('Unable to create date from %s', txt)
                elif order[i] == 'partnum':
                    section = None
                    reobj = re.search('Part[\s-]*\w+', txt)
                    if reobj:
                        partnum = txt[reobj.start():reobj.end()]
                        if len(txt) > reobj.end():
                            txt = txt[reobj.end():]
                            txt = txt.strip(' -\t\r\n')
                            if txt:
                                section = txt
                    else:
                        partnum = txt    
                    metainfo['partnum'] = partnum
                    if section:
                        metainfo['section'] = section

                elif order[i] in ['subject', 'extraordinary_type']:
                    metainfo[order[i]] = txt                    
 
            i += 1
        if metainfo.get_date() == dateobj:
            metainfo.set_gztype('Extraordinary')
            minfos.append(metainfo)

