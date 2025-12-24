import datetime
import re
import os
import urllib.parse
from http.cookiejar import CookieJar

from .basegazette import BaseGazette
from ..utils import utils

class MadhyaPradesh(BaseGazette):
    def __init__(self, name, storage):
        BaseGazette.__init__(self, name, storage)
        self.baseurl  = 'https://govtpress.mp.gov.in/gazette'
        self.pageurl_tmpl = 'https://govtpress.mp.gov.in/Gazette/ajaxPaginationData/{}'

        self.hostname = 'govtpress.mp.gov.in'


    def get_postdata(self, year, pagenum):
        postdata = (
            ('page', f'{(pagenum - 1)*10}'),
            ('sTitle', ''),
            ('ci_csrf_token', ''),
            ('cat_id', ''),
            ('department_id', ''),
            ('year', f'{year}'),
        )

        return postdata

    def find_column_order(self, tr):
        order = []
        for td in tr.find_all('th'):
            txt = utils.get_tag_contents(td)
            if txt and re.search('\u0936\u094d\u0930\u0947\u0923\u0940', txt):
                order.append('gztype')
            elif txt and re.search('\u0935\u093f\u0937\u092f', txt):
                order.append('subject')
            elif txt and re.search('\u0935\u093f\u092d\u093e\u0917', txt):
                order.append('department')
            elif txt and re.search('\u0926\u093f\u0928\u093e\u0902\u0915', txt):
                order.append('date')
            elif txt and re.search('\u0930\u093e\u091c\u092a\u0924\u094d\u0930\s+\u0915\u094d\u0930.', txt):
                order.append('gznum')
            elif txt and re.search('\u0930\u093e\u091c\u092a\u0924\u094d\u0930\s+\u092a\u094d\u0930\u0915\u093e\u0930', txt):
                order.append('part')
            elif txt and re.search('\u0932\u093f\u0902\u0915', txt):
                order.append('download')
            else:
                order.append('')

        if 'subject' in order and 'date' in order and 'gznum' in order:
            return order

        return None     

    def process_row(self, metainfos, tr, order):
        metainfo = utils.MetaInfo()
        i = 0
        for td in tr.find_all('td'):
            txt = utils.get_tag_contents(td)
            if txt and order[i] in ['subject', 'department', 'gznum']:
                txt, n = re.subn('\s+', ' ', txt)
                if txt.strip() != '':
                    metainfo[order[i]] = txt.strip()

            elif txt and order[i] == 'date':
                try:
                    d = datetime.datetime.strptime(txt.strip(), '%d-%m-%Y').date()
                    metainfo.set_date(d)
                except Exception:
                    self.logger.warning('Could not parse date %s', txt)

            elif txt and order[i] == 'part':
                txt, n = re.subn('\s+', ' ', txt)
                if txt.strip() != '':
                    match = re.match(r'^.*-\s*(\d+)$', txt, re.IGNORECASE)
                    if match:
                        metainfo['partnum'] = int(match.group(1).strip())
                        # Assume Ordinary for parts
                        metainfo.set_gztype('Ordinary')

            elif txt and order[i] == 'gztype':
                if txt.strip() != '':
                    match = re.match(r'^\u0905\u0938\u093e\u0927\u093e\u0930\u0923\s+\u0930\u093e\u091c\u092a\u0924\u094d\u0930$', txt, re.IGNORECASE)
                    if match:
                        metainfo.set_gztype('Extraordinary')
                    else:
                        metainfo.set_gztype('Ordinary')

            elif order[i] == 'download':
                link = td.find('a')
                if link:
                    href = link.get('href')
                    if href:
                        gzurl = urllib.parse.urljoin(self.baseurl, href)
                        metainfo.set_url(gzurl)
                    
            i += 1

        for k in ['gztype', 'gznum', 'date', 'url']:
            if k not in metainfo:
                self.logger.warning('Ignoring as not enough info to download: %s', metainfo)
                return

        metainfos.append(metainfo)


    def parse_results(self, webpage, fromdate, todate, pagenum):
        metainfos = []
        has_nextpage = False

        d = utils.parse_webpage(webpage, self.parser)
        if not d:
            self.logger.warning('Unable to parse gazette list page')
            return metainfos, has_nextpage

        table = d.find('table')
        if not table:
            self.logger.warning('Unable to find result table in gazette list page')
            return metainfos, has_nextpage

        order = None
        for tr in table.find_all('tr'):
            if not order:
                order = self.find_column_order(tr)
                continue
            
            self.process_row(metainfos, tr, order)

        pagination_ul = d.find('ul', {'class': 'pagination'})
        nextpage = utils.find_next_page(pagination_ul, pagenum)
        if nextpage:
            has_nextpage = True

        return metainfos, has_nextpage

    def download_metainfo(self, metainfo, dls):

        filename = f"{metainfo['gztype']}_{metainfo['gznum']}"
        if 'partnum' in metainfo:
            filename = f"{filename}_Part-{metainfo['partnum']}"
        filename, n = re.subn('\s+', '-', filename)

        relpath = os.path.join(self.name, metainfo.get_date().__str__()) 
        relurl = os.path.join(relpath, filename)

        if self.save_gazette(relurl, metainfo['url'], metainfo):
            dls.append(relurl)


    def sync_oneyear(self, year, dls, fromdate, todate, event):

        cookiejar = CookieJar()

        response = self.download_url(self.baseurl, savecookies = cookiejar)
        if not response or not response.webpage:
            self.logger.warning('Unable to download gazette list page for year %d', year)
            return

        has_nextpage = True
        pagenum = 1

        while has_nextpage and not event.is_set():
            self.logger.info('Processing gazette list page %d for year %d', pagenum, year)
            postdata = self.get_postdata(year, pagenum)
            pageurl = self.pageurl_tmpl.format((pagenum - 1)*10)
            response = self.download_url(pageurl, postdata = postdata,
                                         loadcookies = cookiejar, savecookies = cookiejar,
                                         headers = {'X-Requested-With': 'XMLHttpRequest'})
            if not response or not response.webpage:
                self.logger.warning('Unable to download gazette list page %d for year %d', pagenum, year)
                return

            metainfos, has_nextpage = self.parse_results(response.webpage, fromdate, todate, pagenum)

            for metainfo in metainfos:
                if metainfo.get_date() < fromdate.date() or metainfo.get_date() > todate.date():
                    continue
                self.download_metainfo(metainfo, dls)

            pagenum += 1



    def get_years(self, fromdate, todate):
        years = set()

        from_year = fromdate.year
        to_year   = todate.year
        years = set()
        while from_year <= to_year:
            years.add(from_year)
            from_year += 1

        years = list(years)
        years.sort()
        return years

    def sync(self, fromdate, todate, event):
        dls = []

        years = self.get_years(fromdate, todate)

        for year in years:
            self.sync_oneyear(year, dls, fromdate, todate, event)
            if event.is_set():
                break
        self.logger.info(f'Got {len(dls)} Gazettes from {fromdate.date()} to {todate.date()}')
        return dls

class MadhyaPradeshOld(BaseGazette):
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
                                
                metainfo = utils.MetaInfo()
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
        metainfo = utils.MetaInfo()
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
