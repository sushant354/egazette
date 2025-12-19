from http.cookiejar import CookieJar
import re
import os
import base64
import datetime
import urllib.parse

from ..utils import utils
from ..utils import ext_ops

from .basegazette import BaseGazette

class Gujarat(BaseGazette):
    def __init__(self, name, storage):
        BaseGazette.__init__(self, name, storage)
        self.baseurl      = 'https://egazette.gujarat.gov.in/GazettesSearch.aspx'
        self.hostname     = 'egazette.gujarat.gov.in'
        self.search_endp  = './GazettesSearch.aspx'
        self.result_table = 'ContentPlaceHolder1_gvDocumentList'
        self.all_metainfos = None


    def get_column_order(self, tr):
        order = []
        for td in tr.find_all('th'):
            txt = utils.get_tag_contents(td)
            if txt and re.search(r'Issue\s+No', txt):
                order.append('gznum')
            elif txt and re.search(r'Gazette\s+Type', txt):
                order.append('gztype')
            elif txt and re.search(r'Download', txt):
                order.append('download')
            elif txt and re.search(r'Department', txt):
                order.append('department')
            elif txt and re.search(r'Gazette\s+Part', txt):
                order.append('partnum')
            elif txt and re.search(r'Govt\.\s+Press', txt):
                order.append('publisher')
            elif txt and re.search(r'Gazette\s+Date', txt):
                order.append('gzdate')
            else:
                order.append('')
        return order

    def find_next_page(self, tr, curr_page):
        classes = tr.get('class')

        dotlink = None
        if classes and 'GridPager' in classes:
            for td in tr.find_all('td'):
                if td.find('table') is not None:
                    continue

                link = td.find('a')
                if link is None:
                    continue
                
                txt = utils.get_tag_contents(td).strip()
                if txt:
                    try: 
                        page_no = int(txt)
                        dotlink = None
                    except Exception:
                       if txt == '...':
                            dotlink = link
                       page_no = None

                    if page_no == curr_page + 1:
                        return link

        if dotlink is not None:
            return dotlink

        return None

    def process_result_row(self, tr, metainfos, dateobj, order):
        metainfo = utils.MetaInfo()

        i = 0
        for td in tr.find_all('td'):
            if len(order) > i:
                col = order[i]

                txt = utils.get_tag_contents(td)
                if txt:
                    txt = txt.strip()

                if col == 'gztype':
                    metainfo.set_gztype(txt)    

                elif col == 'download':
                    link = td.find('a')
                    if link:
                        metainfo[col] = link 

                elif col != '':
                    metainfo[col] = txt

            i += 1

        if 'download' in metainfo:
            metainfos.append(metainfo)

    def get_option_for_year(self, select_tag, year):
        val = ''

        options = select_tag.find_all('option')

        for option in options:
            if option.text.strip() == str(year):
                val = option.get('value')
                break

        return val

    def get_post_data(self, tags, dateobj, remove_buttons):
        postdata = []

        for tag in tags:
            name  = None
            value = None

            if tag.name == 'input':
                name  = tag.get('name')
                value = tag.get('value')
                t     = tag.get('type')

                if t == 'submit' and remove_buttons:
                    continue

                if name == 'ctl00$ContentPlaceHolder1$txtFromDate':
                    fromdateobj = dateobj - datetime.timedelta(days=1)
                    value = fromdateobj.strftime('%d/%m/%Y')

                elif name == 'ctl00$ContentPlaceHolder1$txtToDate':
                    value = dateobj.strftime('%d/%m/%Y')

            elif tag.name == 'select':        
                name = tag.get('name')
                if name == 'ctl00$ContentPlaceHolder1$cmbYear':
                    value = self.get_option_for_year(tag, dateobj.year)

            if name:
                if value is None:
                    value = ''

                postdata.append((name, value))

        return postdata


    def get_form_data(self, webpage, dateobj, remove_buttons=False):

        search_form = utils.get_search_form(webpage, self.parser, self.search_endp)
        if search_form is None:
            self.logger.warning('Unable to find search form for date: %s', dateobj)
            return None

        reobj    = re.compile('^(input|select)$')
        inputs   = search_form.find_all(reobj)
        postdata = self.get_post_data(inputs, dateobj, remove_buttons)

        return postdata

    def download_nextpage(self, nextpage, postdata, search_url, cookiejar):
        newdata = []

        href = nextpage.get('href') 
        if not href:
            return None

        groups = []
        for reobj in re.finditer("'(?P<obj>[^']+)'", href):
            groups.append(reobj.groupdict()['obj'])

        if len(groups) < 2:
            return None

        etarget = groups[0]    
        page_no = groups[1]
            
        for k, v in postdata:
            if k == '__EVENTTARGET':
                newdata.append((k, etarget))
            elif k == '__EVENTARGUMENT':
                newdata.append((k, page_no))
            elif k in ['btnDetail', 'btnSubmit']:
                continue
            else:
                newdata.append((k, v))

        response = self.download_url(search_url, savecookies = cookiejar, \
                                     referer = search_url, \
                                     loadcookies = cookiejar, \
                                     postdata = newdata)
            
        return response 


    def parse_search_results(self, webpage, dateobj, curr_page):
        metainfos = []
        nextpage  = None

        d = utils.parse_webpage(webpage, self.parser)
        if not d:
            self.logger.warning('Unable to parse search result page for %s', dateobj)
            return metainfos, nextpage

        tables = d.find_all('table', {'id': self.result_table})

        if len(tables) != 1:
            self.logger.warning('Could not find the result table for %s', dateobj)
            return metainfos, nextpage
        
        order = None
        for tr in tables[0].find_all('tr'):
            if not order:
                order = self.get_column_order(tr)
                continue

            if nextpage is None:
                nextpage = self.find_next_page(tr, curr_page)
                if nextpage is not None:
                    continue

            if tr.find('input') is None and tr.find('a') is None:
                continue

            self.process_result_row(tr, metainfos, dateobj, order)

        return metainfos, nextpage

    def download_metainfos(self, relpath, metainfos, dateobj, search_url, cookiejar):
        dls = []

        for metainfo in metainfos:
            metainfo = metainfo.copy()
            link = metainfo.pop('download')
            url  = link.get('href')
            if not url:
                continue

            gznum = metainfo['gznum']
            if gznum == '--':
                del metainfo['gznum']

            gzdate_str = metainfo.pop('gzdate').strip()
            try:
                gzdate = datetime.datetime.strptime(gzdate_str, '%d/%m/%Y').date()
            except Exception:
                try:
                    year = int(gzdate_str)
                    gzdate = datetime.datetime(year, 1, 1).date()
                except Exception:
                    self.logger.warning('Unable to parse "%s" as date for %s', gzdate_str, dateobj)
                    continue

            if gzdate != dateobj:
                continue

            parsed_url = urllib.parse.urlparse(url)
            docid = urllib.parse.parse_qs(parsed_url.query)['docid'][0]

            if not docid.endswith('.pdf'):
                self.logger.warning('Got non pdf doc: %s', docid)
                continue

            docid = docid[:-4]

            gzurl = urllib.parse.urljoin(search_url, url)

            year = dateobj.year
            if year < 2021:
                metainfo['year'] = year
                relpath = '/'.join(relpath.split('/')[:-1])
                relpath = os.path.join(relpath, f'{dateobj.year}')
            else:
                metainfo.set_date(dateobj)

            relurl = os.path.join(relpath, docid)
                
            saved = self.save_gazette(relurl, gzurl, metainfo)
            if saved:
                dls.append(relurl)

        return dls

    def pull_gazette(self, gurl, referer = None, postdata = None,
                     cookiefile = None, headers = {},
                     encodepost = True):

        response = BaseGazette.pull_gazette(self, gurl, referer = referer, postdata = postdata,
                                            cookiefile = cookiefile, headers = headers,
                                            encodepost = encodepost)

        if response is None or response.webpage is None:
            return None

        if response.srvresponse.get('Content-Type', '').lower() == 'application/pdf':
            return response

        d = utils.parse_webpage(response.webpage, self.parser)
        if not d:
            self.logger.warning('Unable to parse download page from %s', gurl)
            return None

        obj = d.find('object')
        if not obj or not obj.get('data'):
            self.logger.warning('Unable to locate data in page from %s', gurl)
            return None

        data = obj.get('data')
        data = data.replace('data:application/pdf;base64,', '')

        doc = base64.b64decode(data)
        response.webpage = doc

        return response

    def is_valid_gazette(self, doc, min_size):
        mtype = ext_ops.get_buffer_type(doc)

        if mtype == 'text/html':
            with open('temp.html', 'wb') as f: 
                f.write(doc)
            return False

        return BaseGazette.is_valid_gazette(self, doc, min_size)
        

    def download_oneday(self, relpath, dateobj):
        dls = []
        cookiejar = CookieJar()

        year = dateobj.year
        if year < 2021 and dateobj != datetime.datetime(year, 1, 1).date():
            return dls

        response = self.download_url(self.baseurl, savecookies = cookiejar)
        if not response or not response.webpage:
            self.logger.warning('Could not fetch %s for the day %s', self.baseurl, dateobj)
            return dls

        curr_url = response.response_url

        if year == 2021 and self.all_metainfos is not None:
            relurls = self.download_metainfos(relpath, self.all_metainfos, dateobj, \
                                              curr_url, cookiejar)
            dls.append(relurls)
            return dls

        postdata = self.get_form_data(response.webpage, dateobj)
        postdata = utils.remove_fields(postdata, set(['ctl00$ContentPlaceHolder1$btnClear']))

        response = self.download_url(self.baseurl, postdata = postdata, referer = curr_url, \
                                     savecookies = cookiejar, loadcookies = cookiejar)

        self.all_metainfos = []
        
        pagenum = 1
        while response is not None and response.webpage is not None:
            curr_url = response.response_url

            metainfos, nextpage = self.parse_search_results(response.webpage, \
                                                            dateobj, pagenum)

            if year == 2021:
                self.all_metainfos.extend(metainfos)
            relurls = self.download_metainfos(relpath, metainfos, dateobj, \
                                              curr_url, cookiejar)
            dls.extend(relurls)

            if not nextpage:
                break

            pagenum += 1

            self.logger.info('Going to page %d for date %s', pagenum, dateobj)
            postdata = self.get_form_data(response.webpage, dateobj, remove_buttons=True)
            response = self.download_nextpage(nextpage, postdata, curr_url, cookiejar)
 

        return dls