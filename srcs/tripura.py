from http.cookiejar import CookieJar
import re
import os
from PIL import Image
import io
import json
import datetime
import urllib.request
import urllib.parse
import urllib.error

from .basegazette import BaseGazette
from ..utils import utils
from ..utils import decode_captcha
import time as t

'''
Tripura egazette server invalidates captcha regardless of the proper value when ever ordinary gazette type is selected
Only Gazette type 2 (Extra-Ordinary): [ddlntype], is being returned by the server
The server also returns multiple pdfs on a single day, ordered by from-to date
Verified that the server is able to return only Extra-Ordinary Gazette pdfs and No ordinary gazettes regardless of the selection,
Master Token has been disabled in the website (commented-out), the serever does not require a master token. 
'''

class TripuraBase(BaseGazette):
    def __init__(self, name, storage):
        BaseGazette.__init__(self, name, storage)
        self.baseurl      = 'https://egazette.tripura.gov.in/egazette/'
        self.hostname     = 'egazette.tripura.gov.in'
        self.search_endp  = 'newsearchresultpage.jsp'
        self.gztype       = ''                              # Can't set as the server rejects captcha
        self.captcha_url  = 'CaptchaGen?timestamp=%s'       # Pass time

        self.pdf_table_ref = 'home.jsp'
        self.pdf_file_hash = 'AjaxServlet'                  # Gets file hash
        self.html_pdf_embedding = 'Reports/viewSearchDocument.jsp?aid=%s~1&hash=%s'             # Pass extracted value from the table row for the pdf, pass pdf file hash

        self.headers = {
            'Accept': 'image/avif,image/webp,image/apng,image/svg+xml,image/*,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.9',
            'Connection': 'keep-alive',
            'Sec-Fetch-Dest': 'image',
            'Sec-Fetch-Mode': 'no-cors',
            'Sec-Fetch-Site': 'same-origin',
            'sec-ch-ua': '"Google Chrome";v="147", "Not.A/Brand";v="8", "Chromium";v="147"',
            'sec-ch-ua-mobile': '?0',
            'sec-ch-ua-platform': '"Linux"',
        }

        self.search_headers = {
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7',
            'Accept-Language': 'en-US,en;q=0.9',
            'Cache-Control': 'max-age=0',
            'Connection': 'keep-alive',
            'Content-Type': 'application/x-www-form-urlencoded',
            'Origin': f'https://{self.hostname}',
            'Sec-Fetch-Dest': 'document',
            'Sec-Fetch-Mode': 'navigate',
            'Sec-Fetch-Site': 'same-origin',
            'Sec-Fetch-User': '?1',
            'Upgrade-Insecure-Requests': '1',
            'sec-ch-ua': '"Google Chrome";v="147", "Not.A/Brand";v="8", "Chromium";v="147"',
            'sec-ch-ua-mobile': '?0',
            'sec-ch-ua-platform': '"Linux"',
        }

        self.hash_headers = {
            'Accept': '*/*',
            'Accept-Language': 'en-US,en;q=0.9',
            'Connection': 'keep-alive',
            'Content-Type': 'application/x-www-form-urlencoded; charset=UTF-8',
            'Origin': f'https://{self.hostname}',
            'X-Requested-With': 'XMLHttpRequest',
            'Sec-Fetch-Dest': 'empty',
            'Sec-Fetch-Mode': 'cors',
            'Sec-Fetch-Site': 'same-origin',
            'sec-ch-ua': '"Google Chrome";v="147", "Not.A/Brand";v="8", "Chromium";v="147"',
            'sec-ch-ua-mobile': '?0',
            'sec-ch-ua-platform': '"Linux"',
        }

    def get_new_captcha_value(self, cookiejar, referer):
        captcha_url = urllib.parse.urljoin(self.baseurl, self.captcha_url % int(t.time() * 1000))

        response = self.download_url(captcha_url, loadcookies = cookiejar, referer = referer, headers = self.headers)
        if response is None or response.webpage is None:
            self.logger.warning('Unable to download captcha')
            return None

        img = Image.open(io.BytesIO(response.webpage))

        captcha_val = decode_captcha.tripura(img)

        return captcha_val

    # <get_post_data> Not being called by any function, we're building the postdata with <build_search_postdata> function, without scraping them from the website
    # When the website behaves properly and accepts gazette type without rejecting the captcha, we can use this function
    # Or we can set the gazette type manually inside of the <build_search_postdata> function to check if the gazette type is available and download the gazettes
    # This only works if the server response is proper, currently server responds only to ExtraOrdinary Gazette     
    def get_post_data(self, tags, fromdate, todate):
        fromstr = fromdate.strftime('%Y-%m-%d')
        tostr   = todate.strftime('%Y-%m-%d')
        postdata = []

        for tag in tags:
            name  = None
            value = None

            if tag.name == 'input':
                name  = tag.get('name')
                value = tag.get('value')

                if name == 'txtdatefrom':
                    value = fromstr
                elif name == 'txtdateto':
                    value = tostr

            elif tag.name == 'select':        
                name = tag.get('name')
                value = utils.get_selected_option(tag)

                if name == 'ddlntype':
                    value = self.gztype

            if name:
                if value is None:
                    value = ''
                postdata.append((name, value))

        return postdata


    def solve_captcha(self, cookiejar):
        referer = self.baseurl + self.search_endp
        captcha_value = self.get_new_captcha_value(cookiejar, referer)
        if captcha_value:
            self.logger.info("Solved captcha: %s", captcha_value)
            return captcha_value

        self.logger.warning("Error solving captcha, Re-trying")
        for try_count in range(4):
            t.sleep(1)
            captcha_value = self.get_new_captcha_value(cookiejar, referer)
            if captcha_value:
                self.logger.info("Solved captcha: %s", captcha_value)
                return captcha_value
            self.logger.error("Error solving captcha, Re-trying %s", try_count + 1)

        self.logger.error("Failed to solve captcha after all retries")
        return None

    def build_search_postdata(self, fromdate, todate, captcha_value):
        fromstr = fromdate.strftime('%Y-%m-%d')
        tostr   = todate.strftime('%Y-%m-%d')

        return [
            ('searchtype',     'G'),
            ('ddldepartment',  ''),
            ('ddlntype',       self.gztype),
            ('ddlcatory',      ''),
            ('ddlsector',      ''),
            ('ddlpolicy',      ''),
            ('txtgazno',       ''),
            ('txtnotificno',   ''),
            ('txtkeyword',     ''),
            ('txtdatefrom',    fromstr),
            ('txtdateto',      tostr),
            ('txtcaptchadata', captcha_value),
        ]

    def get_results_table(self, webpage):
        d = utils.parse_webpage(webpage, self.parser)
        if d is None:
            self.logger.error("Unable to get gazette pdfs table")
            return None

        results_table = d.find('table', {'id': 'searchResultTable'})
        if results_table:
            self.logger.info("Found gazette pdfs table")
            return results_table
        
        self.logger.info("Gazette pdfs table Not Found!")
        return results_table

    def process_row(self, metainfos, tr, order):
        metainfo = utils.MetaInfo()

        i = 0
        for td in tr.find_all('td'):
            if len(order) > i:
                col = order[i]

                txt = utils.get_tag_contents(td)
                if txt:
                    txt = txt.strip()

                if col == 'date':
                    issuedate = datetime.datetime.strptime(txt, '%d/%m/%Y').date()
                    metainfo.set_date(issuedate)

                #elif col == 'gztype':
                #    if txt == 'Extra-Ordinary':
                #        metainfo.set_gztype('Extraordinary')
                #    else:
                #        metainfo.set_gztype('Ordinary')

                elif col == 'download':
                    btn = td.find('button', {'name': 'viewDeptRouteDocument'})
                    if btn and btn.get('value'):
                        metainfo['doc_id'] = btn.get('value')

                elif col != '':
                    metainfo[col] = txt
            i += 1

            # Tripura website does not provide gazette type column, we need to set by observing the API call
            # Tripura server only returns extraordinary gazette, reject captcha when a gazette type is set in browser, even when the captcha is correct
            if self.gztype:
                if self.gztype == '2':
                    metainfo.set_gztype('Extraordinary')
                else:
                    metainfo.set_gztype('Ordinary')

        if 'doc_id' in metainfo:
            metainfos.append(metainfo)

    def get_result_order(self, tr):
        order = []

        for td in tr.find_all('th'):
            txt = utils.get_tag_contents(td)
            if txt and re.search('Notification-No', txt):
                order.append('notification_num')

            elif txt and re.search('Date', txt):
                order.append('date')

            elif txt and re.search('Category', txt):
                order.append('category')

            elif txt and re.search('Department', txt):
                order.append('department')

            elif txt and re.search('Notification-Type', txt):
                order.append('gztype')

            elif txt and re.search('Gazette\s+No', txt):
                order.append('gznum')

            elif txt and re.search('Sector', txt):
                order.append('sector')

            elif txt and re.search('Policy', txt):
                order.append('policy')

            elif txt and re.search('Organization', txt):
                order.append('organization')

            elif txt and (re.search('Download', txt) or re.search('Action', txt) or re.search('View', txt)):
                order.append('download')

            else:
                order.append('')

        return order

    def parse_results(self, results_table):
        metainfos = []
        order = None

        for tr in results_table.find_all('tr'):
            if order is None:
                order = self.get_result_order(tr)
                continue

            self.process_row(metainfos, tr, order)

        return metainfos

    def get_file_hash(self, doc_id, cookiejar):
        ajax_url = self.baseurl + self.pdf_file_hash
        postdata = [
            ('generate_hash', '1'),
            ('param', doc_id),
        ]

        referer = self.baseurl + self.search_endp

        response = self.download_url(ajax_url, postdata=postdata, loadcookies=cookiejar, savecookies=cookiejar, referer=referer, headers=self.hash_headers)
        if response is None or response.webpage is None:
            self.logger.warning('Unable to get file hash for doc_id %s', doc_id)
            return None

        file_hash = response.webpage.decode('utf-8').strip()
        return file_hash

    def get_pdf_url(self, doc_id, file_hash, cookiejar):
        embed_url = self.baseurl + self.html_pdf_embedding % (doc_id.split('~')[0], file_hash)
        referer = self.baseurl + self.search_endp

        response = self.download_url(embed_url, loadcookies=cookiejar,
                                     savecookies=cookiejar, referer=referer)
        if response is None or response.webpage is None:
            self.logger.warning('Unable to get embedded pdf page for doc_id %s', doc_id)
            return None

        d = utils.parse_webpage(response.webpage, self.parser)
        if d is None:
            return None

        obj_tag = d.find('object', {'type': 'application/pdf'})
        if obj_tag and obj_tag.get('data'):
            return urllib.parse.urljoin(self.baseurl, obj_tag['data'])

        self.logger.warning('Unable to find pdf object tag for doc_id %s', doc_id)
        return None

    def download_metainfos(self, dls, metainfos, cookiejar, relpath):
        for metainfo in metainfos:
            doc_id = metainfo.pop('doc_id')

            file_hash = self.get_file_hash(doc_id, cookiejar)
            if file_hash is None:
                continue

            pdf_url = self.get_pdf_url(doc_id, file_hash, cookiejar)
            if pdf_url is None:
                continue

            relurl = os.path.join(relpath, doc_id.replace('~', '_'))

            if self.save_gazette(relurl, pdf_url, metainfo):
                dls.append(relurl)

    # Not being called by any function as the server is not using master token
    # Marking as depricated for now, can be removed if the upcoming update also has no master token 
    def get_master_token(self, cookiejar, fromdate, todate, referer):

        jsurl = self.baseurl + "JavaScriptServlet"

        response = self.download_url(jsurl, loadcookies = cookiejar, \
                                    referer = referer, savecookies = cookiejar)
        if response is None or response.webpage is None:
            self.logger.warning('Unable to download javascript at %s for %s to %s', \
                                jsurl, fromdate, todate)
            return None

        js_text = response.webpage.decode('utf-8')
        match = re.search(r"var\s+masterTokenValue\s+=\s+'(?P<token>.*)';", js_text)
        if match is None:
            self.logger.warning('Unable to find master token in javascript for %s to %s', \
                                fromdate, todate)
            return None

        master_token = match.group('token')

        return master_token

    # Not called by anyone, Marking as DEPRICATED can be removed in the upcoming update
    def update_token(self, master_token, cookiejar, fromdate, todate, referer):

        jsurl = self.baseurl + "JavaScriptServlet"

        headers = {
            'X-Requested-With': 'XMLHttpRequest', 
            'Nicegazettesecurity': master_token,
            'Origin': f'https://{self.hostname}',
            'Host': self.hostname
        }

        response = self.download_url(jsurl, loadcookies = cookiejar,
                                     referer = referer, savecookies = cookiejar,
                                     headers = headers, method = 'POST')
        if response is None or response.webpage is None:
            self.logger.warning('Unable to download javascript at %s for %s to %s', \
                                jsurl, fromdate, todate)
            return None

        js_text = response.webpage.decode('utf-8')
        data = json.loads(js_text)
        pageTokens = data.get('pageTokens', {})
        new_token = pageTokens.get(self.search_endp, None)
        if new_token is None:
            return master_token

        return new_token

    # The server returns multiple pdfs for a single day, required by the log to provide number of pdfs published for that day
    def filter_by_date(self, metainfos, fromdate, todate):
        filtered = []
        for m in metainfos:
            d = m.get_date()
            if d and fromdate <= d <= todate:
                filtered.append(m)
        return filtered

    def download_oneday(self, relpath, dateobj):
        dls = []
        cookiejar = CookieJar()
        fromdate  = dateobj
        todate    = dateobj

        search_url = self.baseurl + self.search_endp
        home_url   = self.baseurl + self.pdf_table_ref

        response = self.download_url(search_url, savecookies=cookiejar, referer=home_url, headers=self.headers)
        if response is None or response.webpage is None:
            self.logger.warning('Unable to download search page for %s', dateobj)
            return dls

        t.sleep(1)

        captcha_value = self.solve_captcha(cookiejar)
        if captcha_value is None:
            return dls

        postdata = self.build_search_postdata(fromdate, todate, captcha_value)

        response = self.download_url(search_url, postdata=postdata,
                                     referer=home_url,
                                     loadcookies=cookiejar, savecookies=cookiejar,
                                     headers=self.search_headers)
        if response is None or response.webpage is None:
            self.logger.warning('Unable to get search results for %s', dateobj)
            return dls

        results_table = self.get_results_table(response.webpage)
        if results_table is None:
            self.logger.warning('No results table found for %s', dateobj)
            return dls

        metainfos = self.parse_results(results_table)
        if not metainfos:
            self.logger.info('No results found for %s', dateobj)
            return dls

        filtered = self.filter_by_date(metainfos, fromdate, todate)
        self.logger.info('Found %d total results, %d in date range for %s',
                         len(metainfos), len(filtered), dateobj)

        self.download_metainfos(dls, filtered, cookiejar, relpath)

        return dls

class TripuraOrdinary(TripuraBase):
    def __init__(self, name, storage):
        TripuraBase.__init__(self, name, storage)
        self.gztype = '1'

class TripuraExtraOrdinary(TripuraBase):
    def __init__(self, name, storage):
        TripuraBase.__init__(self, name, storage)
        self.gztype = '2'