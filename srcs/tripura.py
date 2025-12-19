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


class TripuraBase(BaseGazette):
    def __init__(self, name, storage):
        BaseGazette.__init__(self, name, storage)
        self.baseurl      = 'https://egazette.tripura.gov.in/egazette/'
        self.hostname     = 'egazette.tripura.gov.in'
        self.search_endp  = '/egazette/newsearchresultpage.jsp'
        self.gztype       = ''

    def get_captcha_value(self, cookiejar, referer):
        captcha_url = urllib.parse.urljoin(self.baseurl, 'CaptchaGen')

        response = self.download_url(captcha_url, loadcookies = cookiejar, referer = referer)
        if response is None or response.webpage is None:
            self.logger.warning('Unable to download captcha')
            return None

        img = Image.open(io.BytesIO(response.webpage))

        captcha_val = decode_captcha.tripura(img)

        return captcha_val
        
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


    def get_form_data(self, webpage, cookiejar, curr_url, fromdate, todate):
        search_form = utils.get_search_form(webpage, self.parser, self.search_endp)
        if search_form is None:
            self.logger.warning('Unable to locate search form for %s to %s', fromdate, todate)
            return None

        reobj  = re.compile('^(input|select)$')
        inputs = search_form.find_all(reobj)
        postdata = self.get_post_data(inputs, fromdate, todate)

        captcha_value = self.get_captcha_value(cookiejar, curr_url)
        if captcha_value is None:
            return None

        postdata.append(('txtkeyword', ''))
        postdata.append(('txtcaptchadata', captcha_value))
        postdata.append(('btns', ''))

        return postdata

    def get_results_table(self, webpage):
        d = utils.parse_webpage(webpage, self.parser)
        if d is None:
            return None

        results_table = d.find('table', {'id': 'qryresults'})

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

                elif col == 'gztype':
                    if txt == 'Extra-Ordinary':
                        metainfo.set_gztype('Extraordinary')
                    else:
                        metainfo.set_gztype('Ordinary')

                elif col == 'download':
                    link = td.find('a')
                    if link and link.get('href'):
                        metainfo['href'] = link.get('href')

                elif col != '':
                    metainfo[col] = txt
            i += 1

        if 'href' in metainfo:
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

            elif txt and re.search('Download', txt):
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

    def download_metainfos(self, dls, metainfos, curr_url, relpath):
        for metainfo in metainfos:
            href   = metainfo.pop('href')
            gzurl  = urllib.parse.urljoin(curr_url, href)

            #parsed   = urllib.parse.urlparse(href)
            #bencoded = urllib.parse.parse_qs(parsed.query)['bencode'][0]
            #bdecoded = base64.b64decode(base64.b64decode(bencoded))
            #gztslno  = int(bdecoded)

            gznum  = metainfo['gznum']
            relurl  = os.path.join(relpath, f'{gznum}')

            if self.save_gazette(relurl, gzurl, metainfo):
                dls.append(relurl)


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

    def download_oneday(self, relpath, dateobj):
        dls = []
        cookiejar = CookieJar()
        fromdate  = dateobj
        todate    = dateobj

        response = self.download_url(self.baseurl, savecookies = cookiejar)
        if response is None or response.webpage is None:
            self.logger.warning('Unable to download page at %s for %s to %s', \
                                self.baseurl, fromdate, todate)
            return dls


        results_table = None
        search_url = None

        while results_table is None:
            curr_url = response.response_url

            import time
            time.sleep(5)

            master_token = self.get_master_token(cookiejar, fromdate, todate, curr_url)
            if master_token is None:
                return dls

            postdata = self.get_form_data(response.webpage, cookiejar, \
                                          curr_url, fromdate, todate)
            if postdata is None:
                return dls

            master_token = self.update_token(master_token, cookiejar, fromdate, todate, curr_url)

            postdata.append(('NICeGazetteSecurity', master_token))


            search_url = urllib.parse.urljoin(curr_url, self.search_endp)
            search_url += f'?NICeGazetteSecurity={master_token}'

            response = self.download_url(search_url, postdata = postdata, referer = curr_url, \
                                         loadcookies = cookiejar, savecookies = cookiejar)
            if response is None or response.webpage is None:
                self.logger.warning('Unable to get search results at %s for %s to %s', \
                                    search_url, fromdate, todate)
                return dls

            results_table = self.get_results_table(response.webpage)

        metainfos = self.parse_results(results_table)

        self.download_metainfos(dls, metainfos, curr_url, relpath)

        return dls

class TripuraOrdinary(TripuraBase):
    def __init__(self, name, storage):
        TripuraBase.__init__(self, name, storage)
        self.gztype = '1'

class TripuraExtraOrdinary(TripuraBase):
    def __init__(self, name, storage):
        TripuraBase.__init__(self, name, storage)
        self.gztype = '2'