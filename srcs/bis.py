import re
import os
from io import BytesIO
import urllib.request, urllib.parse, urllib.error
import datetime
from http.cookiejar import CookieJar
import hashlib
from PIL import Image

from ..utils import utils, decode_captcha
from .basegazette import BaseGazette
#dummy345654 test345654*
class BIS(BaseGazette):
    def __init__(self, name, storage):
        BaseGazette.__init__(self, name, storage)

        self.hostname   = 'standardsbis.bsbedge.com'
        self.baseurl    = 'https://standardsbis.bsbedge.com'
        self.loginurl   = urllib.parse.urljoin(self.baseurl, '/BIS_Login')
        self.captchaurl = urllib.parse.urljoin(self.baseurl, '/Handler.ashx')
        self.searchurl  = urllib.parse.urljoin(self.baseurl, '/BIS_AdvanceSearchScope')
        self.parser     = 'html.parser'
        self.cookiejar  = CookieJar()
        self.solve_captcha = decode_captcha.bis_captcha
        i = 0
        while i <= 5:
            success = self.login()
            if success:
                break
            i += 1


    def fetch_captcha(self, count):
        if count >= 10:
            return None
        captcha = self.download_url(self.captchaurl, \
                                    loadcookies = self.cookiejar, \
                                    savecookies = self.cookiejar)
        if not captcha:
            self.logger.warning('Unable to download captcha')
            return None

        img = Image.open(BytesIO(captcha.webpage))
        captcha_val = self.solve_captcha(img)
        if  not captcha_val:
            return self.fetch_captcha(count + 1)
        return captcha_val

    def sha256(self, val):
        m = hashlib.sha256()
        m.update(val.encode('utf8'))
        return m.hexdigest()

    def fetch_login_page(self):
        response = self.download_url(self.loginurl, savecookies=self.cookiejar)
        if not response or not response.webpage or response.error:
            return None

        return response.webpage 

    def get_login_data(self, webpage, username, passwd):
        d = utils.parse_webpage(webpage, self.parser)
        if not d:
            self.logger.warning('Unable to parse login page')
            return None

        captcha_val = self.fetch_captcha(0)
        if not captcha_val:
            self.logger.warning('Unable to decode captcha')
            return None

        form = d.find('form', {'name': 'aspnetForm'})
        postdata = []
        salt_inp = form.find('input', {'name': 'ctl00$ContentPlaceHolder1$T1$HDSalt'})
        if not salt_inp:
            self.logger.warn('Could not get password salt')
            return None
        salt = salt_inp.get('value')
        if salt:
            passwd = self.sha256 (self.sha256(passwd) + salt)
        else:    
            passwd = self.sha256 (self.sha256(passwd))

        for inputbt in form.find_all('input'):
            name = inputbt.get('name')
            value = inputbt.get('value')
            if name:
                if name == 'ctl00$ContentPlaceHolder1$T1$txtUser':
                    value = username
                elif name == 'ctl00$ContentPlaceHolder1$T1$txtPass':
                    value = passwd
                elif name == 'ctl00$ContentPlaceHolder1$T1$captcha':
                    value = captcha_val 
                elif name == 'ctl00$ContentPlaceHolder1$T1$HDSalt':
                    value = ''
                elif name == '__EVENTTARGET':
                    value = 'ctl00$ContentPlaceHolder1$T1$btn_submit'

                if value == None:
                    value = ''
                postdata.append((name, value))

        return postdata

    def login(self):
        webpage = self.fetch_login_page()
        if not webpage:
            return False
        
        postdata = self.get_login_data(webpage, 'dummy345654@yahoo.com', 'stds4free')

        response = self.download_url(self.loginurl, postdata = postdata, \
                       loadcookies = self.cookiejar, savecookies=self.cookiejar)

        if response == None or response.webpage == None:
            return False 
        d = utils.parse_webpage(response.webpage, self.parser)
        if not d:
            return False

        span = d.find('span', {'id': 'ctl00_ContentPlaceHolder1_T1_lblnotice'})
        if span:
            txt = utils.get_tag_contents(span)
            if txt and re.search('Captcha\s+code\s+did\s+not\s+match', txt):
                return False

        return True

    def scope_search(self, relpath, dateobj):
        dls = []
        response = self.download_url(self.searchurl, \
                       loadcookies = self.cookiejar, savecookies=self.cookiejar)

        if not response or not response.webpage:
            self.logger.warning('Unable to download search results for %s', dateobj)
            return dls

        d = utils.parse_webpage(response.webpage, self.parser)
        if not d:
            self.logger.warning('Unable to parse search page')
            return dls

        d1 = self.search(d, dateobj,  'ctl00$ContentPlaceHolder1$btn_search')
        if not d:
            return dls

        dls = self.process_search_results(d1, relpath, dateobj)

        while True:
            next_page = d1.find('a', {'id':'ctl00_ContentPlaceHolder1_T1_lbtnNext'})
            if not next_page:
                break

            self.logger.info('Going to the next page for %s', dateobj)
            d1= self.search(d, dateobj, 'ctl00$ContentPlaceHolder1$T1$lbtnNext')
            if not d1:
                self.logger.warning('Unable to download next page %s', dateobj)
                break 
            dls.extend(self.process_search_results(d1, relpath, dateobj))
        return dls

    def search(self, d, dateobj, event_target):
        postdata = self.get_search_data(d, dateobj, event_target) 

        response = self.download_url(self.searchurl, postdata = postdata, \
                       loadcookies = self.cookiejar, savecookies=self.cookiejar)

        if not response or not response.webpage:
            self.logger.warning('Unable to download search results for %s', dateobj)
            return None

        d = utils.parse_webpage(response.webpage, self.parser)
        if not d:
            self.logger.warning('Unable to parse search results page %s', dateobj)
            return None
        return d

    def process_search_results(self, d, relpath, dateobj):
        dls = []
        minfos = self.parse_search_results(d, dateobj)
        for metainfo in minfos:
            href = metainfo.get('href')
            num  = metainfo.get('num')
            if not num:
                continue 

            num, n = re.subn('\s+', '', num)
            relurl = os.path.join(relpath, num)

            if not href:
                if self.storage_manager.save_metainfo(self.name, relurl, metainfo):
                    self.logger.info('Saved metainfo %s' % relurl)
                    dls.append(relurl)
                continue

            stdurl = urllib.parse.urljoin(self.searchurl, href)

            if self.storage_manager.should_download_raw(relurl, stdurl):
                count = 0
                while count < 5 and self.download_standard(metainfo, relurl, stdurl) == False:
                    count += 1
                if count < 5:    
                    dls.append(relurl)

            elif self.storage_manager.save_metainfo(self.name, relurl, metainfo):
                 self.logger.info('Saved metainfo %s' % relurl)
                 dls.append(relurl)

        return dls

    def download_standard(self, metainfo, relurl, stdurl):
        response = self.download_url(stdurl,  loadcookies = self.cookiejar, \
                                     savecookies=self.cookiejar)
        if not response or not response.webpage:
            return False 
        d = utils.parse_webpage(response.webpage, self.parser)
        form = d.find('form', {'id': 'form1'})
        if not form:
            return False
        href = form.get('action')
        captcha = self.fetch_captcha(0)

        postdata = self.get_download_data(form, captcha)
        dlurl = urllib.parse.urljoin(stdurl, href)

        if self.save_gazette(relurl, dlurl, metainfo, postdata = postdata, \
                             cookiefile = self.cookiejar):
            return True
        return False 

    def is_valid_gazette(self, doc, min_size):
        extension = self.storage_manager.get_file_extension(doc)
        if extension != 'pdf':
            return False
        return True

    def parse_search_results(self, d, dateobj):
        minfos = []

        for div in d.find_all('div', {'class': 'div_abc_main'}):
            metainfo = self.get_meta_info (div)
            metainfo.set_date(dateobj)
            minfos.append(metainfo)

        return minfos

    def get_meta_info(self, div):
        metainfo = utils.MetaInfo()
        title_div = div.find('div', {'class': 'div-abc1'})
        if title_div:
            title_spans = title_div.find_all('span')
            if len(title_spans) > 0:
                txt = utils.get_tag_contents(title_spans[0])
                metainfo['num'] = txt.strip()
      
            i = 0
            desc = [] 
            for span in title_spans:
                txt = utils.get_tag_contents(span)
                txt = txt.strip()

                spanid = span.get('id')
                spanstyle = span.get('style') 
                if spanstyle:
                    spanstyle = spanstyle.strip()

                if spanid == None and spanstyle == 'font-size: 15px;':
                    metainfo.set_title(txt)
                elif re.search('Technical\s+Committee', txt) and span.nextSibling:
                    txt = '%s'  % span.nextSibling
                    metainfo['committee'] = txt.strip()
                elif re.search('Superseeded\s+by', txt) and span.nextSibling:
                    txt = '%s'  % span.nextSibling
                    metainfo['superseeded'] = txt.strip()
                elif i > 0:
                    desc.append(txt)
                i += 1    
        if desc:
            metainfo['info'] = ' '.join(desc)

        statusdiv = div.find('div', {'class': 'div-abc2'})
        if statusdiv:
            spans = div.find_all('span')
            for span in spans:
                spanid = span.get('id')
                if spanid and re.search('lblstatus$', spanid):
                    metainfo['status'] = utils.get_tag_contents(span)

            for link in div.find_all('a'):
                linkid = link.get('id')
                if linkid and re.search('noanmds$', linkid):
                    metainfo['numamendments'] = utils.get_tag_contents(link)

        dldiv = div.find('div', {'class': 'div-abc3'})
        if dldiv:
            link = dldiv.find('a', {'class': 'quickview'})
            if link:
                metainfo.set_href(link.get('href'))

            for span in dldiv.find_all('span'):
                spanid = span.get('id')
                if spanid and re.search('lblPrintPrice$', spanid):
                    metainfo['inr'] = utils.get_tag_contents(span)

                if spanid and re.search('lblPrintPriceUSD$', spanid):
                    metainfo['usd'] = utils.get_tag_contents(span)

        return metainfo

    def get_search_data(self, d, dateobj, event_target):
        form = d.find('form', {'name': 'aspnetForm'})
        datestr  = utils.dateobj_to_str(dateobj, '-', reverse = True)
        postdata = [('ctl00$ToolkitScriptManager1', \
                    'ctl00$ContentPlaceHolder1$UpdatePanel1|%s' % event_target)]

        inputbts = form.find_all('input')
        
        for inputbt in inputbts:
            name = inputbt.get('name')
            value = inputbt.get('value')
            if name:
                if name == 'ctl00$ContentPlaceHolder1$txt_pub_date_from':
                    value = datestr
                elif name == 'ctl00$ContentPlaceHolder1$txt_pub_date_to':
                    value = datestr
                elif name == '__EVENTTARGET':
                    value = event_target 
                elif name == 'ctl00$ContentPlaceHolder1$btn_search':
                    continue
                elif name == 'ctl00$ContentPlaceHolder1$T1$btn_refresh_wish':
                    continue

                if value == None:
                    value = ''
                postdata.append((name, value))

        if event_target == 'ctl00$ContentPlaceHolder1$T1$lbtnNext':
            postdata.append(('ctl00$ContentPlaceHolder1$T1$HiddenField1', '0'))
        postdata.append(('hiddenInputToUpdateATBuffer_CommonToolkitScripts', '1'))

        postdata.append(('__ASYNCPOST', 'true'))

        return postdata


    def get_download_data(self, form, captcha):
        postdata = []
        for inputbt in form.find_all('input'):
            name = inputbt.get('name')
            value = inputbt.get('value')
            if name:
                if name == 'CheckBox2':
                    value = 'on'
                elif name == '__EVENTTARGET':
                    value = 'btn_submit'
                elif name == 'captcha':
                    value = captcha

                if value == None:
                    value = ''
                postdata.append((name, value))

        return postdata

    def download_oneday(self, relpath, dateobj):
        dls = []

        dls = self.scope_search(relpath, dateobj)
        return dls


