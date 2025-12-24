import re
import os
import urllib.request, urllib.parse, urllib.error
import datetime

from ..utils import utils
from .basegazette import BaseGazette

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
        metainfo = utils.MetaInfo()
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


class OdishaGovPress(BaseGazette):
    def __init__(self, name, storage):
        BaseGazette.__init__(self, name, storage)
        self.ordinary_url = 'https://govtpress.odisha.gov.in/en/light/odisha-gazettes'
        self.extraordinary_url = 'https://govtpress.odisha.gov.in/en/light/ex-ordinary-gazettes'
        self.hostname = 'govtpress.odisha.gov.in'
        self.page_cache = {}

    def download_url_cached(self, url):

        if url not in self.page_cache:
            response = self.download_url(url)

            self.page_cache[url] = response

        return self.page_cache[url]

    def find_field_order(self, tr):
        order  = []

        for th in  tr.find_all('th'):
            txt = utils.get_tag_contents(th)

            if txt and re.search(r'Department', txt):
                order.append('department')
            elif txt and re.search(r'Notification\s+No', txt):
                order.append('notification_num')
            elif txt and re.search(r'Gazette\s+No', txt):
                order.append('gznum')
            elif txt and re.search(r'Download', txt):
                order.append('download')
            elif txt and re.search(r'Gazette\s+Date', txt):
                order.append('gzdate')
            elif txt and re.search(r'Notification\s+Date', txt):
                order.append('notification_date')
            elif txt and re.search(r'Week\s+No', txt):
                order.append('weeknum')
            else:
                order.append('')
        
        for field in ['download', 'gzdate', 'gznum']:
            if field not in order:
                return None

        return order
                
    def process_row(self, metainfos, tr, order):
        metainfo = utils.MetaInfo()

        i = 0
        for td in tr.find_all('td'):
            txt = utils.get_tag_contents(td)
            txt = txt.strip()
            col = order[i]
            if col == 'gzdate':
                gzdate = datetime.datetime.strptime(txt, '%d-%m-%Y').date()
                metainfo.set_date(gzdate)
            elif col == 'download':
                link = td.find('a')
                if link and link.get('href'):
                    metainfo['download'] =  link.get('href')
            elif col == 'gznum':
                txt = txt.replace('`', '')
                metainfo[col] = txt
            elif col != '':
                metainfo[col] = txt

            i += 1

        if 'download' not in metainfo:
            return

        if metainfo.get_date().year < 1000:
            notidate_str = metainfo['notification_date'] 
            notidate = datetime.datetime.strptime(notidate_str, '%d-%m-%Y').date()
            metainfo.set_date(notidate)

        metainfos.append(metainfo)
                
    def parse_results(self, webpage, dateobj):
        metainfos = []

        d = utils.parse_webpage(webpage, self.parser)
        if not d:
            self.logger.warning('Unable to parse result page date %s', dateobj)
            return metainfos

        order = None
        for table in d.find_all('table'):
            for tr in table.find_all('tr'):
                if order == None:
                    order = self.find_field_order(tr)
                    continue

                self.process_row(metainfos, tr, order)
                 
        return metainfos
  
    def download_oneday(self, relpath, dateobj):
        dls = []
        
        for url, gztype in [(self.extraordinary_url, 'Extraordinary'), \
                            (self.ordinary_url, 'Ordinary')]:
            response = self.download_url_cached(url)
            if response is None or response.webpage is None:
                self.logger('Unable to get the base page for ate %s', dateobj)
                return dls

            metainfos = self.parse_results(response.webpage, dateobj)
        
            for metainfo in metainfos:
                gzdate = metainfo.get_date()
                if gzdate != dateobj:
                    continue
                gzurl = metainfo.pop('download')
                gzurl = urllib.parse.urljoin(url, gzurl)
                relurl = os.path.join(relpath, f'{gztype}_{metainfo['gznum']}')
                metainfo.set_gztype(gztype)
                if self.save_gazette(relurl, gzurl, metainfo):
                    dls.append(relurl)

        return dls        


class OdishaEGazette(BaseGazette):
    def __init__(self, name, storage):
        BaseGazette.__init__(self, name, storage)
        self.hostname = 'egazette.odisha.gov.in'
        self.weekly_url      = 'https://egazette.odisha.gov.in/weekly_archival'
        self.extraordinary_url = 'https://egazette.odisha.gov.in/extraordinary_archival'
        self.other_url     =  ['https://egazette.odisha.gov.in/bills_acts', \
                            'https://egazette.odisha.gov.in/land_acquisition', \
                            'https://egazette.odisha.gov.in/change_of_partnership_details', \
                            'https://egazette.odisha.gov.in/change_name_surname', \
                            'https://egazette.odisha.gov.in/change_gender', \
                            'https://egazette.odisha.gov.in/other_gazette' ]
        self.page_cache = {}

    def download_url_cached(self, url):

        if url not in self.page_cache:
            response = self.download_url(url)

            self.page_cache[url] = response

        return self.page_cache[url]

 
    def get_departments(self):
        depts = []

        response = self.download_url_cached(self.extraordinary_url)
        if not response or not response.webpage:
            self.logger.warning('Unable to get main page')
            return depts

        d = utils.parse_webpage(response.webpage, self.parser)
        if not d:     
            self.logger.warning('Unable to parse main page')
            return depts

        links = d.find_all('a')
        links = [ link for link in links if link.find('div', { 'class': 'dept-card2' }) ]

        for link in links:
            depts.append({
                'url': link.get('href'),
                'name': utils.get_tag_contents(link).strip()
            })

        return depts

    def find_field_order(self, tr):
        order  = []
        for td in tr.find_all('th'):
            txt = utils.get_tag_contents(td)
            if txt and re.search('Department', txt):
                order.append('department')
            elif txt and re.search('Subject', txt):
                order.append('subject')
            elif txt and re.search('Download', txt):
                order.append('download')
            elif txt and re.search('Date', txt):
                order.append('date')
            elif txt and re.search(r'Gazette\s+Number', txt):
                order.append('gznum')
            elif txt and re.search('Week', txt):
                order.append('weeknum')
            elif txt and re.search(r'Issue\s+Date', txt):
                order.append('issuedate')
            else:
                order.append('')
        
        for field in ['download', 'date']:
            if field not in order:
                return None

        return order
         
                
    def process_row(self, metainfos, tr, order):
        metainfo = utils.MetaInfo()

        i = 0
        for td in tr.find_all('td'):
            txt = utils.get_tag_contents(td)
            txt = txt.strip()

            col = order[i]
            v = None
            if col == 'download':
                link = td.find('a')
                if link and link.get('href'):
                    v = link.get('href')
            elif col == 'date':
                try:
                    gzdate = datetime.datetime.strptime(txt, '%d-%m-%Y').date()
                except Exception as e:
                    gzdate = datetime.datetime.strptime(txt, '%Y-%m-%d').date()

                metainfo.set_date(gzdate)
            elif col != '':
                v = txt

            if v:
                metainfo[col] = v

            i += 1

        if 'download' not in metainfo: 
            return

        metainfos.append(metainfo)


    def parse_results(self, webpage, curr_page):
        metainfos = []
        nextpage  = None

        d = utils.parse_webpage(webpage, self.parser)
        if not d:
            return metainfos, nextpage

        tables = d.find_all('table')

        order = None
        for table in tables:
            for tr in table.find_all('tr'):
                if order is None:
                    order = self.find_field_order(tr)
                    continue
                
                self.process_row(metainfos, tr, order)

        pager_ul = d.find('ul', { 'class': 'pagination' })
        if pager_ul is None:
            return metainfos, nextpage

        nextpage = utils.find_next_page(pager_ul, curr_page)

        return metainfos, nextpage
        

    def sync_onedepartment(self, dls, department_url, department_name, \
                           fromdate, todate, event):

        pageno = 1
        response = self.download_url(department_url)
        while response is not None and response.webpage is not None:

            if event.is_set():
                self.logger.warning('Exiting prematurely as timer event is set')
                break

            metainfos, nextpage = self.parse_results(response.webpage, \
                                                    pageno)

            for metainfo in metainfos:
                gzdate = metainfo.get_date()

                if gzdate > todate or gzdate < fromdate:
                    continue

                metainfo.set_gztype('Extraordinary')

                gzurl = metainfo.pop('download')
                docid = gzurl.split('/')[-1]
                docid = docid.rsplit('.', 1)[0]
                docid = f'extraordinary-{docid}'

                relpath = os.path.join(self.name, gzdate.__str__())
                relurl  = os.path.join(relpath, docid)
                if self.save_gazette(relurl, gzurl, metainfo):
                    dls.append(relurl)

            if nextpage is None:
                break

            href = nextpage.get('href')
            if href is None:
                continue

            pageno += 1
            nextpage_url = urllib.parse.urljoin(department_url, href)
            response = self.download_url(nextpage_url)
    
    def sync_weeklygz(self, dls, \
                           fromdate, todate, event):

        pageno = 1
        response = self.download_url(self.weekly_url)
        while response is not None and response.webpage is not None:

            if event.is_set():
                self.logger.warning('Exiting prematurely as timer event is set')
                break

            metainfos, nextpage = self.parse_results(response.webpage, \
                                                     pageno)

            for metainfo in metainfos:
                gzdate = metainfo.get_date()
                if gzdate > todate or gzdate < fromdate:
                    continue

                metainfo.set_gztype('Weekly')

                gzurl = metainfo.pop('download')
                docid = gzurl.split('/')[-1]
                docid = docid.rsplit('.', 1)[0]
                docid = f'Weekly-{docid}'

                relpath = os.path.join(self.name, gzdate.__str__())
                relurl  = os.path.join(relpath, docid)
                if self.save_gazette(relurl, gzurl, metainfo):
                    dls.append(relurl)

            if nextpage is None:
                break

            href = nextpage.get('href')
            if href is None:
                continue

            pageno += 1
            nextpage_url = urllib.parse.urljoin(self.weekly_url, href)
            response = self.download_url(nextpage_url)
    
    def sync_othergz(self, dls, url,\
                           fromdate, todate, event):

        pageno = 1
        response = self.download_url(url)
        while response is not None and response.webpage is not None:

            if event.is_set():
                self.logger.warning('Exiting prematurely as timer event is set')
                break

            metainfos, nextpage = self.parse_results(response.webpage, \
                                                     pageno)

            for metainfo in metainfos:
                gzdate = metainfo.get_date()

                if gzdate > todate or gzdate < fromdate:
                    continue

                metainfo.set_gztype('Extraordinary')

                gzurl = metainfo.pop('download')
                docid = gzurl.split('/')[-1]
                docid = docid.rsplit('.', 1)[0]
                docid = f'Extraordinary-{docid}'

                relpath = os.path.join(self.name, gzdate.__str__())
                relurl  = os.path.join(relpath, docid)
                if self.save_gazette(relurl, gzurl, metainfo):
                    dls.append(relurl)

            if nextpage is None:
                break

            href = nextpage.get('href')
            if href is None:
                continue

            pageno += 1
            nextpage_url = urllib.parse.urljoin(url, href)
            response = self.download_url(nextpage_url)

 
    def sync(self, fromdate, todate, event):
        dls = []

        fromdate = fromdate.date()
        todate   = todate.date()
        departments = self.get_departments()

        for department in departments:
            self.sync_onedepartment(dls, department['url'], department['name'], fromdate, todate, event)

            if event.is_set():
                self.logger.warning('Exiting prematurely as timer event is set')
                break
        
        self.sync_weeklygz(dls, fromdate, todate, event)

        for url in self.other_url:
            self.sync_othergz(dls, url, fromdate, todate, event)
            if event.is_set():
                self.logger.warning('Exiting prematurely as timer event is set')
                break

        self.logger.info(f'Got {len(dls)} Gazettes from {fromdate} to {todate}')
        return dls