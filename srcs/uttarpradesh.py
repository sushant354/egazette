from http.cookiejar import CookieJar
import re
import os
import urllib.parse

from ..utils import utils
from .basegazette import BaseGazette

class UttarPradeshBase(BaseGazette):
    def __init__(self, name, storage):
        BaseGazette.__init__(self, name, storage)
        self.baseurl  = 'https://dpsup.up.gov.in/'
        self.hostname = 'dpsup.up.gov.in'
        self.gztype = ''

    def get_post_data(self, tags, dateobj):
        datestr  = dateobj.strftime('%d/%m/%Y')
        postdata = []

        for tag in tags:
            name  = None
            value = None

            if tag.name == 'input':
                name  = tag.get('name')
                value = tag.get('value')
                if name in [ 'ctl00$ContentPlaceHolder_Body$txtFromDate', \
                             'ctl00$ContentPlaceHolder_Body$txtToDate' ]:
                    value = datestr

            elif tag.name == 'select':        
                name = tag.get('name')
                value = utils.get_selected_option(tag)

            if name:
                if value is None:
                    value = ''
                postdata.append((name, value))

        return postdata


    def get_form_data(self, webpage, curr_url, dateobj):
        parsed = urllib.parse.urlparse(curr_url)
        parsed = parsed._replace(netloc='', scheme='')
        form_href = parsed.geturl()

        search_form = utils.get_search_form(webpage, self.parser, form_href)
        if search_form is None:
            self.logger.warning('Unable to find search form of %s for %s', curr_url, dateobj)
            return None

        reobj  = re.compile('^(input|select)$')
        inputs = search_form.find_all(reobj)

        postdata = self.get_post_data(inputs, dateobj)
        postdata = utils.remove_fields(postdata, set(['ctl00$ContentPlaceHolder_Body$btnReset']))

        return postdata


    def get_column_order(self, tr):
        order  = []

        for td in tr.find_all('th'):
            txt = utils.get_tag_contents(td)
            if txt and re.search('Department', txt):
                order.append('department')
            elif txt and re.search('Gazette\s+Content', txt):
                order.append('subject')
            elif txt and re.search('Gazette\s+No', txt):
                order.append('gznum')
            else:
                order.append('')    
        return order

    def find_next_page(self, tr, curr_page):
        classes = tr.get('class')
        if classes and 'pagination' in classes:
            for link in tr.find_all('a'):
                txt = utils.get_tag_contents(link)
                if txt:
                   try: 
                       page_no = int(txt)
                   except Exception:
                       page_no = None
                   if page_no == curr_page + 1 and link:
                       return link

        return None
 
    def process_result_row(self, metainfos, tr, order, dateobj, gztype):
        metainfo = utils.MetaInfo()
        metainfo.set_date(dateobj)
        metainfo.set_gztype(gztype)

        def add_text(key, node):
            txt = utils.get_tag_contents(node)
            if txt:
                txt = txt.strip()
            if txt:
                metainfo[key] = txt

        i = 0
        for td in tr.find_all('td'):
            if len(order) > i:
                col = order[i]

                if col == 'subject':
                    span = td.find('span', recursive = False)
                    if span:
                        link = span.find('a', recursive = False)
                        if link:
                            add_text('subject', link)
                            href = link.get('href')
                            if href is not None:
                                metainfo['href'] = href

                        subspan = span.find('span')
                        if subspan:
                            txt = utils.get_tag_contents(subspan)
                            reobj = re.search('Language\s+:\s+(")?\s+(?P<lang>\w+)\s+(")?', txt)
                            if reobj:
                                metainfo['language'] = reobj.groupdict()['lang']

                elif col == 'gznum':
                    add_text(col, td)

                elif col == 'department':
                    spans = td.find_all('span', recursive = False)
                    if len(spans) == 2:
                        add_text('department', spans[0])
                        add_text('subdepartment', spans[1])
            i += 1

        if 'href' not in metainfo:
            return

        metainfos.append(metainfo)

    def parse_results(self, webpage, dateobj, curr_page, gztype):
        metainfos = []
        nextpage  = None

        d = utils.parse_webpage(webpage, self.parser)
        if d is None:
            self.logger.warning('Unable to parse results page for %d', dateobj)
            return metainfos, nextpage

        results_table = d.find('table', {'id': 'ContentPlaceHolder_Body_gdvGazetteContent'})
        if results_table is None:
            self.logger.warning('Unable to find results table for %d', dateobj)
            return metainfos, nextpage

        order = None
        for tr in results_table.find_all('tr'):
            if order is None:
                order = self.get_column_order(tr)
                continue

            if nextpage is None:
                nextpage = self.find_next_page(tr, curr_page)
                if nextpage is not None:
                    continue

            self.process_result_row(metainfos, tr, order, dateobj, gztype)

        return metainfos, nextpage

    def download_nextpage(self, nextpage, search_url, postdata, cookiejar):
        href = nextpage.get('href') 
        if not href:
            return None

        groups = []
        for reobj in re.finditer("'(?P<obj>[^']+)'", href):
            groups.append(reobj.groupdict()['obj'])

        if not groups or len(groups) < 2:
            return None

        etarget = groups[0]
        page_no = groups[1]

        postdata = utils.replace_field(postdata, '__EVENTTARGET', etarget)
        postdata = utils.replace_field(postdata, '__EVENTARGUMENT', page_no)

        response = self.download_url(search_url, savecookies = cookiejar, \
                                     referer = search_url, \
                                     loadcookies = cookiejar, \
                                     postdata = postdata)
            
        return response


    def download_metainfo(self, relpath, metainfo, curr_url):
        href = metainfo.pop('href')
        gztype = metainfo.get_gztype()
        gznum = metainfo.pop('gznum')
        if gztype == 'Extraordinary':
            metainfo['notification_num'] = gznum
        else:
            gparts = gznum.split('/')
            metainfo['volume_num'] = gparts[0]
            metainfo['gznum'] = gparts[1]

        if href.startswith('https://drive.google.com'):
            # https://drive.google.com/file/d/THIS_IS_THE_ID/view?usp=drive_link
            docid = href.split('/')[5]
            gzurl = f'https://drive.google.com/uc?export=download&id={docid}'
            docid = f'gdrive-{docid}'
        else:
            gzurl = urllib.parse.urljoin(curr_url, href)

            fname = href.split('/')[-1]
            docid = fname.rsplit('.', 1)[0].lower()

        relurl = os.path.join(relpath, docid)
        if self.save_gazette(relurl, gzurl, metainfo):
            return relurl

        return None


    def download_onetype(self, dls, relpath, dateobj, gztype, url):
        cookiejar = CookieJar()

        response = self.download_url(url, savecookies = cookiejar)
        if response is None or response.webpage is None:
            self.logger.warning('Unable to get %s for %s', url, dateobj)
            return

        curr_url = response.response_url

        postdata = self.get_form_data(response.webpage, curr_url, dateobj)
        if postdata is None:
            return

        response = self.download_url(curr_url, postdata = postdata, savecookies = cookiejar, \
                                     loadcookies = cookiejar, referer = curr_url)

        pagenum = 1
        while response is not None and response.webpage is not None:
            curr_url = response.response_url

            metainfos, nextpage = self.parse_results(response.webpage, dateobj, pagenum, gztype)

            for metainfo in metainfos:
                relurl = self.download_metainfo(relpath, metainfo, curr_url)
                if relurl is not None:
                    dls.append(relurl)

            if nextpage is None:
                break
            
            if postdata is None:
                postdata = self.get_form_data(response.webpage, curr_url, dateobj)
                if postdata is None:
                    break

            pagenum += 1
            self.logger.info('Going to page %d for date %s', pagenum, dateobj)
            response = self.download_nextpage(nextpage, curr_url, postdata, cookiejar)
            postdata = None


class UttarPradeshExtraOrdinary(UttarPradeshBase):
    def __init__(self, name, storage):
        UttarPradeshBase.__init__(self, name, storage)
        self.gztype = 'Extraordinary'
        self.url    ='https://dpsup.up.gov.in/en/gazette?Gazettelistslug=en-extra-ordinary-gazette'

    def download_oneday(self, relpath, dateobj):
        dls = []
        self.download_onetype(dls, relpath, dateobj, self.gztype, self.url)
        return dls
    
class UttarPradeshOrdinary(UttarPradeshBase):
    def __init__(self, name, storage):
        UttarPradeshBase.__init__(self, name, storage)
        self.gztype = 'Ordinary'
        self.url    = 'https://dpsup.up.gov.in/en/gazette?Gazettelistslug=en-ordinary-gazette'
    
    def download_oneday(self, relpath, dateobj):
        dls = []
        self.download_onetype(dls, relpath, dateobj, self.gztype, self.url)
        return dls
