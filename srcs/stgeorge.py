import datetime
import re
import os
import calendar

from .kerala import Kerala
from ..utils import utils
from ..utils.metainfo import MetaInfo


class StGeorge(Kerala):
    def __init__(self, name, storage):
        Kerala.__init__(self, name, storage)
        self.hostname = 'statelibrary.kerala.gov.in'
        self.date_url = 'http://statelibrary.kerala.gov.in/fort_gazette/gazette.php'
        self.baseurl = 'http://statelibrary.kerala.gov.in/fort_gazette/'
        self.parser     = 'html.parser'
        self.save_raw     = False 
        self.gzurl_format = 'sitemedia/TG%s/%s/%s_Page_%s.png' 

    def get_post_data(self, year):        
        postdata = [('action', 'search_Gazette'), ('department', ''), \
            ('gaz_date', ''), ('gaz_eo', '0'), ('gaz_issue_number', ''), \
            ('gaz_month', ''), ('gaz_number', ''), ('gaz_part', ''), \
            ('gaz_volume', ''), ('gaz_year', year), ('order_no', ''), \
            ('order_no_category', 'All'), ('result_start', 0), \
            ('search_string', ''), ('year_category', 'exact')]
        return postdata

    def download_dates(self, relpath, fromdate, todate):
        year = fromdate.year
        assert year == todate.year

        postdata = self.get_post_data(year)
        response = self.download_url(self.date_url, postdata = postdata)
        if response and response.webpage:
            dls = self.results_page(relpath, response.webpage, year, \
                                    fromdate, todate) 
        else:    
            dls = []

        return dls
    
    def results_page(self, relpath, webpage, year, fromdate, todate):
        dls = []

        while 1:
            minfos, nextpage = self.parse_metainfos(webpage, year, \
                                                    fromdate, todate)
            self.download_gazettes(relpath, minfos, dls)

            if nextpage:
                onclick = nextpage.get('onclick')
                postdata = self.next_page_post(onclick, year)
                if not postdata:
                    self.logger.warning('Unable to get postdata for next page from %s', onclick)
                    break

                response = self.download_url(self.date_url, postdata = postdata)
                if not response or not response.webpage:
                    break
                webpage = response.webpage
            else:
                break        

        return dls          


    def download_gazettes(self, relpath, minfos, dls):
        for metainfo in minfos:
            relurl = metainfo.pop('relurl')
            dateobj = metainfo.get_date()
       
            gurl = metainfo.get_url()
            relurl = os.path.join(relpath, dateobj.__str__(), relurl)

            updated = False
            if self.save_raw and self.storage_manager.should_download_raw(relurl, gurl):
                response = self.download_url(gurl)
 
                doc = response.webpage
                if doc and self.is_valid_gazette(doc, 0):
                    if self.storage_manager.save_rawdoc(self.name, relurl, response.srvresponse, doc):
                        updated = True
                        self.logger.info('Saved rawfile %s' % relurl)
                    else:
                        self.logger.info('not able to save the doc %s' % relurl)


            if self.storage_manager.save_metainfo(self.name, relurl, metainfo):
                self.logger.info('Saved metainfo %s' % relurl)
                updated = True

            if updated:
                dls.append(relurl)

    def parse_metainfos(self, webpage, year, fromdate, todate):
        minfos = []
        nextpage = None

        d = utils.parse_webpage(webpage, self.parser)
        if not d:
            self.logger.warning('Unable to parse results page for year %d', year)
            return minfos


        for td in d.find_all('td'):
            link =  td.find('a') 
            if link == None:
                continue
            img = td.find('img')
            if img:
                title = img.get('title')
                if title == 'Next' and nextpage == None:
                    nextpage = link
                continue
                    
            metainfo = self.get_metainfo(link, td)
            if metainfo:
                dateobj = metainfo.get_date()
                if dateobj and dateobj >= fromdate and dateobj <= todate:
                    minfos.append(metainfo)
                paras = td.find_all('p')

                if len(paras) >= 2:
                    p = paras[1]
                    txt = utils.get_tag_contents(p)
                    reobj = re.search('Department:\s*(?P<dept>.+)\s+Order\s+Nos:\s*(,Othres\s*:)?(?P<ordernum>.*)', txt)
                    if reobj:
                        groupdict = reobj.groupdict()
                        ordernum   = groupdict['ordernum'].strip()
                        metainfo['department'] = groupdict['dept'].strip()
                        if re.match('[\d+(,\s*)?]+$', ordernum):
                            metainfo['ordernum'] = ordernum

                if len(paras) >= 3:        
                    p = paras[2]
                    txt = utils.get_tag_contents(p)
                    if txt:
                        metainfo.set_subject(txt) 

        return minfos, nextpage
         
    def get_metainfo(self, link, td):
        onclick = link.get('onclick')
        if onclick == None:
            return None
        
        reobj = re.search("loadFullImg\(\s*'(?P<gzyear>\w+)'\s*,\s*'(?P<month>\w+)'\s*,\s*'(?P<day>\w+)'\s*,\s*'(?P<accno>\w+)'\s*,\s*(?P<pdf_page>\w+)\s*,\s*(?P<gzpage>\w+)\)", onclick)
        if not reobj:
            return None

        groupdict = reobj.groupdict()
        gzyear    = groupdict['gzyear']
        month     = groupdict['month']
        day       = groupdict['day']
        accno     = groupdict['accno']
        page      = int(groupdict['pdf_page'])
        gzpage    = int(groupdict['gzpage'])

        pagenumber = '%d' % page
        if gzpage >= 10 and gzpage < 100:
            if page < 10:
                pagenumber = '0' + pagenumber
        elif gzpage >= 100 and gzpage < 1000:
            if page < 10:
                pagenumber = '00' + pagenumber
            elif page < 100:
                pagenumber = '0' + pagenumber
        elif gzpage >= 1000:
            if page < 10:
                pagenumber = '000' + pagenumber
            elif page < 100:
                pagenumber = '00' + pagenumber
            elif page < 1000:
                pagenumber = '0' + pagenumber
                    
        month_num = utils.get_month_num(month, calendar.month_abbr)             
        d = datetime.date(int(gzyear), month_num, int(day))

        gzurl = self.baseurl +  self.gzurl_format % (gzyear, accno, accno, pagenumber)

        
        metainfo = MetaInfo()
        metainfo.set_url(gzurl)       
        metainfo.set_date(d)
        metainfo['relurl'] =  '%s_Page_%s' % (accno, pagenumber)

        txt = utils.get_tag_contents(link)
        self.populate_link_metainfo(txt, metainfo)

        return metainfo

    def populate_link_metainfo(self, txt, metainfo):
        reobj = re.search('Issue\s+Number:\s*(?P<num>\d+)', txt)
        if reobj:
            metainfo['issue'] = reobj.groupdict()['num']
            
        reobj = re.search('Part:\s*(?P<num>[^,]+),', txt)
        if reobj:
            metainfo['partnum'] = reobj.groupdict()['num']

        reobj = re.search('Gazette\s+Page:\s*(?P<num>\d+)', txt)
        if reobj:
            metainfo['gzpage'] = reobj.groupdict()['num']

    def next_page_post(self, onclick, year):
        reobj = re.search('recordPagination\("(?P<query>[^"]+)"\s*,\s*(?P<start>\d+)\s*,\s*(?P<page>\d+)', onclick)
        if reobj:
            groupdict = reobj.groupdict()
            self.logger.info('Next page %s for year %s', groupdict['page'], year)

            postdata  = [('action',       'row_pagination'), \
                         ('current_page', groupdict['page']), \
                         ('query',        groupdict['query']), \
                         ('row_start',    groupdict['start'])]
        else:
            postdata = None
        return postdata

class KeralaLibrary(StGeorge):
    def __init__(self, name, storage):
        StGeorge.__init__(self, name, storage)
        self.hostname = 'statelibrary.kerala.gov.in'
        self.date_url = 'http://statelibrary.kerala.gov.in/gazette/gazette.php'
        self.baseurl = 'http://statelibrary.kerala.gov.in/gazette/'
        self.parser     = 'html.parser'
        self.save_raw     = False 
        self.gzurl_format = 'sitemedia/%s/%s/%s_Page_%s.png'
         
    def populate_link_metainfo(self, txt, metainfo):
        reobj = re.search('Issue\s+Number:\s*(?P<num>\d+)', txt)
        if reobj:
            metainfo['issue'] = reobj.groupdict()['num']
            
        reobj = re.search('Part:\s*(?P<num>.+),?\s*Gazette\s+Page:\s*(?P<gzpage>\w+),', txt)
        if reobj:
            metainfo['partnum'] = reobj.groupdict()['num']
            metainfo['gzpage']  = reobj.groupdict()['gzpage']
     
        reobj = re.search('Volume:?\s*(?P<volume>\w*)\s*Number:\s*(?P<number>\d+)', txt)
        if reobj:
            metainfo['volume'] =  reobj.groupdict()['volume']
            metainfo['number'] =  reobj.groupdict()['number']
