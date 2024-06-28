import datetime
import re
import os
import math
import random
import urllib.request
import urllib.parse
import urllib.error
from http.cookiejar import CookieJar, Cookie

from calmjs.parse import es5
from calmjs.parse.unparsers.extractor import ast_to_dict
from calmjs.parse.asttypes import FunctionCall

from .basegazette import BaseGazette
from ..utils import utils

def tokenize(number):
    token = ''
    charmap = "1234567890abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ*$"
    remainder = number
    while remainder > 0:
        token += charmap[remainder & 0x3F]
        remainder = math.floor(float(remainder) / float(64))
    return token

#{<class 'calmjs.parse.asttypes.String'>: ['allowScriptTagRemoting is false.'], <class 'calmjs.parse.asttypes.FunctionCall'>: [[[[], {'r': 'window.dwr._[0]', <class 'calmjs.parse.asttypes.FunctionCall'>: [['r.handleCallback', ['0', '0', 'mBYbyy7ZXfr7Nx2Au1R$1bKww2p']]]}], []]]}
def get_callback_args(ast_dict):
    try:
        return ast_dict[FunctionCall][0][0][1][FunctionCall][0][1]
    except Exception:
        return None

class KeralaCompose(BaseGazette):
    def __init__(self, name, storage):
        BaseGazette.__init__(self, name, storage)
        self.start_date = datetime.datetime(2021, 10, 2)
        self.baseurl    = 'https://compose.kerala.gov.in'
        self.searchurl  = 'https://compose.kerala.gov.in/egazettelink1'
        self.hostname   = 'compose.kerala.gov.in'

    def make_dwr_call(self, script_name, method_name, cookiejar, curr_url, dateobj, \
                      sessionid = None, need_session = True, \
                      batchid = 0, extra_args = {}):
        if sessionid is None and need_session:
            self.logger.error('sessionid not set while making a dwr call to %s.%s for %s', \
                              script_name, method_name, dateobj) 
            return None

        curr_page = urllib.parse.urlparse(curr_url).path
        curr_page = urllib.parse.quote_plus(curr_page)
        
        dwr_path = f'/dwr/call/plaincall/{script_name}.{method_name}.dwr'
        dwr_url = urllib.parse.urljoin(self.baseurl, dwr_path)
        
        sessionid_str = ''
        if sessionid is not None:
            rand = int(random.random() * int(1E16))
            epochtime = int(datetime.datetime.now().strftime('%s'))
            sessionid_str = f'{sessionid}/{tokenize(epochtime)}-{tokenize(rand)}'

        post_data = {
            'callCount': '1',
            'windowName': '',
            'c0-scriptName': script_name,
            'c0-methodName': method_name,
            'c0-id': '0',
            'batchId': batchid,
            'page': curr_page,
            'instanceId': '0',
            'scriptSessionId': sessionid_str
        }
        post_data.update(extra_args)

        post_data_strs = []
        for k,v in post_data.items():
            post_data_strs.append(f'{k}={v}')

        post_data_full_str = '\n'.join(post_data_strs)
        post_data_full_bytes = post_data_full_str.encode('utf-8')
        
        headers = { 'Content-Type': 'text/plain' }
        response = self.download_url(dwr_url, postdata = post_data_full_bytes, loadcookies = cookiejar, \
                                     referer = curr_url, headers = headers, encodepost = False)
        if response is None or response.webpage is None:
            self.logger.warning('Unable to make dwr call to %s.%s for %s', \
                                script_name, method_name, dateobj)
            return None

        txt = response.webpage.decode('utf-8')
        try:
            js_resp = es5(txt)
        except Exception:
            self.logger.warning('Unable to parse response as js for %s', dateobj)
            return None
        js_dict = ast_to_dict(js_resp)
        callback_args = get_callback_args(js_dict)
        if callback_args is None:
            self.logger.warning('Unable to get callback arguments for %s', dateobj)
            return None

        if len(callback_args) != 3:
            self.logger.warning('Unexpected callback arguments for %s', dateobj)
            return None
        return callback_args[2]

    def get_dwr_post_args_extraordinary(self, dateobj):
        datestr = dateobj.strftime('%Y-%m-%d')
        year = dateobj.year
        args = {
            'c0-param0'  : f'string:{year}',
            'c0-param1'  : 'string:none',
            'c0-param2'  : 'string:none',
            'c0-param3'  : 'string:',
            'c0-param4'  : 'string:3',
            'c0-param5'  : 'string:none',
            'c0-param6'  : 'string:',
            'c0-param7'  : 'string:',
            'c0-param8'  : 'string:',
            'c0-param9'  : 'string:none',
            'c0-param10' : 'string:none',
            'c0-param11' : 'string:none',
            'c0-param12' : 'string:none',
            'c0-param13' : 'string:none',
            'c0-param14' : 'string:none',
            'c0-param15' : 'string:none',
            'c0-param16' : f'string:{datestr}',
            'c0-param17' : f'string:{datestr}',
        }
        return args

    def get_dwr_post_args_ordinary(self, dateobj):
        datestr = dateobj.strftime('%Y-%m-%d')
        year = dateobj.year
        args = {
            'c0-param0'  : f'string:{year}',
            'c0-param1'  : 'string:none',
            'c0-param2'  : 'string:none',
            'c0-param3'  : 'string:',
            'c0-param4'  : 'string:2',
            'c0-param5'  : 'string:none',
            'c0-param6'  : 'string:',
            'c0-param7'  : 'string:',
            'c0-param8'  : 'string:',
            'c0-param9'  : 'string:',
            'c0-param10' : 'string:',
            'c0-param11' : 'string:',
            'c0-param12' : 'string:',
            'c0-param13' : 'string:',
            'c0-param14' : 'string:',
            'c0-param15' : 'string:',
            'c0-param16' : 'string:',
            'c0-param17' : 'string:',
        }
        return args

    def get_download_form_data(self, webpage):
        d = utils.parse_webpage(webpage, self.parser)
        if d is None:
            return None
        
        form = d.find('form', { 'id': 'downloadform' })
        if form is None:
            return None

        tags = form.find_all('input')
        formdata = []
        for tag in tags:
            name = tag.get('name')
            formdata.append((name, ''))
        return formdata

    def get_metainfos_extraordinary(self, results, dateobj):
        minfos = []
        for result in results:
            metainfo = utils.MetaInfo()
            metainfo.set_date(dateobj)

            metainfo['gztype'] = 'Extraordinary'
            metainfo['gznum'] = result[1]
            metainfo['department'] = result[4]
            metainfo['office'] = result[6]
            metainfo['subject'] = result[7]
            metainfo['num'] = result[3]

            minfos.append(metainfo)

        return minfos

    def get_metainfos_ordinary(self, results, dateobj):
        minfos = []
        for result in results:
            epochtime_ms = result[5][1][0]
            gzdate = datetime.datetime.fromtimestamp(epochtime_ms/1000).date()
            if gzdate != dateobj:
                continue

            metainfo = utils.MetaInfo()
            metainfo.set_date(dateobj)

            metainfo['gztype'] = 'Ordinary'
            metainfo['part'] = result[0]
            metainfo['gznum'] = result[1]
            metainfo['department'] = result[4]
            metainfo['num'] = result[3]

            minfos.append(metainfo)

        return minfos

    def download_onetype(self, relpath, dateobj, gztype):
        dls = []

        cookiejar = CookieJar()
        response = self.download_url(self.baseurl, savecookies = cookiejar)
        if not response or not response.webpage:
            self.logger.warning('Unable to get base page for day: %s', dateobj)
            return dls
        curr_url = response.response_url

        dwr_sessionid = self.make_dwr_call('__System', 'generateId', cookiejar, curr_url, dateobj, \
                                           need_session = False)
        cookie = Cookie(0, 'DWRSESSIONID', dwr_sessionid, None, False, \
                        self.hostname, True, False, '/', True, False, \
                        None, False, None, None, None)
        cookiejar.set_cookie(cookie) 

        response = self.download_url(self.searchurl, savecookies = cookiejar, \
                                     loadcookies = cookiejar, referer = curr_url)
        if not response or not response.webpage:
            self.logger.warning('Unable to get search page for day: %s', dateobj)
            return dls
        curr_url = response.response_url

        if gztype == 'Extraordinary':
            postargs = self.get_dwr_post_args_extraordinary(dateobj)
        else:
            postargs = self.get_dwr_post_args_ordinary(dateobj)

        results = self.make_dwr_call('gazetteUploadDAO', 'getgazettesearchData', cookiejar, curr_url, dateobj, \
                                     sessionid = dwr_sessionid, need_session = False, extra_args = postargs)
        if results is None:
            return dls

        formdata = self.get_download_form_data(response.webpage)
        if formdata is None:
            self.logger.warning('Unable to get download form data for day: %s', dateobj)
            return dls

        if gztype == 'Extraordinary':
            metainfos = self.get_metainfos_extraordinary(results, dateobj)
        else:
            metainfos = self.get_metainfos_ordinary(results, dateobj)

        for metainfo in metainfos:
            num = metainfo.pop('num')

            formdata = utils.replace_field(formdata, 'searchpdfid', num)
            query_str = urllib.parse.urlencode(formdata).encode('utf-8')
            url = urllib.parse.urljoin(self.baseurl, 'kgSearchfiledownloadpdf')
            url = f'{url}?{query_str}'

            metainfo['url'] = url

            gztype = metainfo['gztype'].lower()
            relurl = os.path.join(relpath, f'{gztype}-{num}')   
            if self.save_gazette(relurl, metainfo['url'], metainfo, cookiefile = cookiejar):
                dls.append(relurl)

        return dls

    def download_oneday(self, relpath, dateobj):
        edls = self.download_onetype(relpath, dateobj, 'Extraordinary')
        odls = self.download_onetype(relpath, dateobj, 'Ordinary')
        return edls + odls

class Kerala(BaseGazette):
    def __init__(self, name, storage):
        BaseGazette.__init__(self, name, storage)
        self.hostname = 'www.egazette.kerala.gov.in'
        self.latest_url = 'http://www.egazette.kerala.gov.in/'
        self.baseurl    = self.latest_url
        self.parser     = 'html.parser'
        self.start_date   = datetime.datetime(2007, 1, 1)

        self.year_href =  '/%d.php'

    def sync(self, fromdate, todate, event):
        newdownloads = []
        while fromdate <= todate:
            if event.is_set():
                self.logger.warning('Exiting prematurely as timer event is set')
                break

            dateobj   = fromdate.date()
            lastdate  = datetime.datetime(fromdate.year, 12, 31)
            if todate < lastdate:
                lastdate = todate
            lastdate = lastdate.date()

            self.logger.info('Dates:  %s to %s', dateobj, lastdate)

            dls = self.download_dates(self.name, dateobj, lastdate)

            self.logger.info('Got %d gazettes between  %s and %s' % (len(dls), dateobj, lastdate))
            newdownloads.extend(dls)
            fromdate = datetime.datetime(fromdate.year + 1, 1, 1)

        return newdownloads

    def download_dates(self, relpath, fromdate, todate):
        year = fromdate.year
        assert year == todate.year
        
        dls = []

        if year < 2007:
            self.logger.warning('Sorry no data for the year %s', year)
            return dls

        href = self.year_href % year
                
        urls = [urllib.parse.urljoin(self.baseurl, href)]
        if year == datetime.date.today().year:
            urls.append(self.latest_url)

        for url in urls:
            response = self.download_url(url)
            if not response or not response.webpage:
                self.logger.warning('Unable to download %s. Skipping %s to %s', url, fromdate, todate)
                continue
            d = utils.parse_webpage(response.webpage, self.parser)
            if not d:
                self.logger.warning('Unable to parse %s. Skipping %s to %s', url, fromdate, todate)
                continue

            minfos = self.process_listing_page(url, d, fromdate, todate)
            for metainfo in minfos:     
                relurl = self.get_relurl(metainfo)
                dateobj = metainfo.get_date()
                if not relurl or not dateobj:
                    self.logger.warning('Skipping. Could not get relurl/date for %s', metainfo)
                    continue

                relurl = os.path.join(relpath, dateobj.__str__(), relurl)
                gurl   = metainfo['url']

                if self.save_gazette(relurl, gurl, metainfo):
                    dls.append(relurl)
        return dls

    def get_relurl(self, metainfo):
        gurl  = metainfo['url']
        words = gurl.split('/')
        if len(words) == 0:
            return None

        filename = '.'.join(words[-1].split('.')[:-1])
        wordlist = [filename]

        pathwords = words[:-1]
        pathwords.reverse()

        i = 0
        for word in pathwords: 
            wordlist.append(word)
            if word.startswith('part') or i >= 3:
                break
            i += 1
        wordlist.reverse()
            
        relurl = '_'.join(wordlist)
        relurl, n = re.subn('[.\s-]+', '-', relurl)
        return relurl

    def process_listing_page(self, baseurl, d, fromdate, todate):
        minfos = []
        for link in d.find_all('a'):
            txt = utils.get_tag_contents(link)
            if not txt:
                continue

            dateobj = utils.get_date_from_title(txt)
            if not dateobj:
                self.logger.warning('Unable to extract date from %s', txt)
                continue

            if dateobj < fromdate or dateobj > todate:
                continue

            href = link.get('href')
            if not href:
                continue

            url = urllib.parse.urljoin(baseurl, href)
            minfos.extend(self.datepage_metainfos(url, dateobj))       
        return minfos

    def datepage_metainfos(self, url, dateobj):
        minfos = []
        response = self.download_url(url)

        if not response or not response.webpage:
            self.logger.warning('Unable to download %s. Skipping', url)
            return minfos

        d = utils.parse_webpage(response.webpage, self.parser)
        if not d:
            self.logger.warning('Unable to parse %s. Skipping.', url)
            return minfos

        partnum = None
        dept    = None
        for td in d.find_all('td'):
            colspan = td.get('colspan')
            links   = td.find_all('a')
            if colspan == '2' and len(links) == 0:
                partnum =  utils.get_tag_contents(td)
                partnum  = utils.remove_spaces(partnum)
                dept    = None
            elif len(links) > 0:
                reobj  = re.compile('^(strong|a)$')
                for x in td.find_all(reobj):
                    if x.name == 'strong':
                        dept = utils.get_tag_contents(x)
                        dept = utils.remove_spaces(dept)
                    elif x.name == 'a'  and partnum:
                        href  = x.get('href')
                        if not href.startswith('../pdf'):
                            continue

                        title = utils.get_tag_contents(x)
                        title = utils.remove_spaces(title)

                        metainfo = utils.MetaInfo()
                        minfos.append(metainfo)

                        metainfo.set_title(title)
                        metainfo.set_date(dateobj)     
                        metainfo['partnum'] = partnum
                        if dept:
                            metainfo['department']    = dept
                        gzurl = urllib.parse.urljoin(url, href)
                        metainfo['url'] = gzurl

        return minfos    
