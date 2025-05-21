from http.cookiejar import CookieJar
import re
import os
from PIL import Image
import io
import urllib.request, urllib.parse, urllib.error

from .andhra import AndhraArchive
from ..utils import utils
from ..utils import decode_captcha

import ssl

ssl._create_default_https_context = ssl._create_unverified_context
class Haryana(AndhraArchive):
    def __init__(self, name, storage):
        AndhraArchive.__init__(self, name, storage)
        self.baseurl      = 'https://www.egazetteharyana.gov.in/home.aspx'
        self.hostname     = 'www.egazetteharyana.gov.in'
        self.search_endp  = 'home.aspx'
        self.result_table = 'ContentPlaceHolder1_GridView1'
        self.captcha_url  = urllib.parse.urljoin(self.baseurl, '/Handler.ashx')
        self.gazette_js   = 'window.open\(\'(?P<href>Gazette[^\']+)'
        self.captcha_field = 'ctl00$ContentPlaceHolder1$txtcaptcha'
        self.solve_captcha = decode_captcha.haryana_captcha
        self.search_button = 'ctl00$ContentPlaceHolder1$Button1'
        self.counter = 1

    def get_post_data(self, tags, dateobj):
        datestr  = utils.dateobj_to_str(dateobj, '-', reverse = True)
        postdata = []

        radio_set = False
        for tag in tags:
            name  = None
            value = None

            if tag.name == 'input':
                name  = tag.get('name')
                value = tag.get('value')
                t     = tag.get('type')
                if t == 'image' or name == 'ctl00$ContentPlaceHolder1$archiveNotification':
                    continue
                if name == 'ctl00$ContentPlaceHolder1$RadioButtonList1' \
                        and radio_set:
                    continue
         
                if name == 'ctl00$ContentPlaceHolder1$txtstartdate' or \
                        name == 'ctl00$ContentPlaceHolder1$txtenddate':
                    value = datestr
                elif name == 'ctl00$ContentPlaceHolder1$Button1':
                    value = 'Submit'
                elif name == 'ctl00$ContentPlaceHolder1$RadioButtonList1':
                    value = '-1'
                    radio_set = True
            elif tag.name == 'select':
                name = tag.get('name')
                if name == 'BtnSearch':
                    value = 'search'
                elif name == 'ctl00$ContentPlaceHolder1$ddlGazetteCat':
                    value = '-1'
                elif name == 'ctl00$ContentPlaceHolder1$ddldepartment':
                    value = '-1'

            if name:
                if value == None:
                    value = ''
                postdata.append((name, value))
        return postdata

    def is_form_webpage(self, d):
        table = d.find('table', {'id': self.result_table})
        if table != None:
            return False 

        submit = d.find('input', {'name': self.search_button})
        if submit == None:
            return False

        return True

    def get_search_results(self, search_url, dateobj, cookiejar):
        response = self.download_url(search_url, savecookies = cookiejar, \
                                     loadcookies=cookiejar)

        while response and response.webpage: 
            response = self.submit_captcha_form(search_url, response.webpage, \
                                                cookiejar, dateobj)
             
            if not response or not response.webpage:
                break
            d = utils.parse_webpage(response.webpage, self.parser)
            if d and not self.is_form_webpage(d):
                break 
            else:   
                self.logger.warning('Failed in solving captcha. Rerying.')
                cookiejar = CookieJar()
                response = self.download_url(search_url, savecookies = cookiejar)
                
        return response
    
    def get_column_order(self, tr):
        order = []
        for th in tr.find_all('th'):
            txt = utils.get_tag_contents(th)
            if txt and re.search('Department', txt):
                order.append('department')
            elif txt and re.search('Notification\s+No', txt):
                order.append('notification_num')
            elif txt and re.search('Notification\s+Subject', txt):
                order.append('subject')
            elif txt and re.search('Gazette\s+No', txt):
                order.append('gznum')
            elif txt and re.search('Category', txt):
                order.append('category')
            elif txt and re.search('Type', txt):
                order.append('gztype')
            else:
                order.append('')
        return order

    def download_captcha(self, search_url, webpage, cookiejar):
        return self.download_url(self.captcha_url, loadcookies=cookiejar)
             
    def submit_captcha_form(self, search_url, webpage, cookiejar, dateobj): 
        captcha = self.download_captcha(search_url, webpage, cookiejar)
        if captcha == None or captcha.webpage == None:
            self.logger.warning('Unable to download captcha')
            return None

        img = Image.open(io.BytesIO(captcha.webpage))
                    
        #img.save('new_captchas/%d.jpeg' % self.counter)          
        captcha_val = self.solve_captcha(img)
        self.counter += 1

        postdata = self.get_form_data(webpage, dateobj, self.search_endp)
        if postdata == None:
            return None

        newpost = []
        for name, value in postdata:
            if name == self.captcha_field:
                value = captcha_val
            newpost.append((name, value)) 
        response = self.download_url(search_url, savecookies = cookiejar, \
                                   referer = search_url, \
                                   headers = {'Content-Type': 'application/x-www-form-urlencoded'}, \
                                   loadcookies = cookiejar, postdata = newpost)
        return response

    def process_result_row(self, tr, metainfos, dateobj, order):
        download = None
        for link in tr.find_all('a'):
            txt = utils.get_tag_contents(link)
            if txt and re.match('\s*Download', txt, re.IGNORECASE):
                download = link.get('href')
                break

        if not download:
            return

        metainfo = utils.MetaInfo()
        metainfos.append(metainfo)
        metainfo.set_date(dateobj)
        metainfo['download'] = download

        i = 0
        for td in tr.find_all('td'):
            if len(order) > i:
                col = order[i]
                txt = utils.get_tag_contents(td)
                if txt:
                    txt = txt.strip()
                else:
                    continue

                if col == 'gznum':
                    metainfo['gznum'] = txt.splitlines()[0]

                elif col in ['subject', 'department', 'notification_num', \
                             'gztype']:
                    metainfo[col] = txt

            i += 1

    def download_metainfos(self, relpath, metainfos, search_url, \
                           postdata, cookiejar):
        dls = []
        for metainfo in metainfos:
            if 'download' not in metainfo or 'notification_num' not in metainfo:
                self.logger.warning('Required fields not present. Ignoring- %s' % metainfo) 
                continue

            href = metainfo.pop('download')
            reobj = re.search('javascript:__doPostBack\(\'(?P<event_target>[^\']+)\'', href)
            if not reobj:
                self.logger.warning('No event_target in the gazette link. Ignoring - %s' % metainfo)
                continue 

            groupdict    = reobj.groupdict()
            event_target = groupdict['event_target']

            newpost = []
            for t in postdata:
                if t[0] == '__EVENTTARGET':
                    t = (t[0], event_target)
                elif t[0] == 'ctl00$ContentPlaceHolder1$ctl03':
                    t = (t[0], '10')
                newpost.append(t)

            num = metainfo['notification_num']
            if 'gztype' in metainfo:
                num = '%s_%s' % (metainfo['gztype'], num)
            num, n = re.subn('[\s/().\[\]]+', '-', num)
            relurl = os.path.join(relpath, num)

            if self.save_gazette(relurl, search_url, metainfo, \
                                 postdata = newpost, referer = search_url, \
                                 cookiefile = cookiejar):
                dls.append(relurl)

        return dls

class HaryanaArchive(Haryana):
    def __init__(self, name, storage):
        Haryana.__init__(self, name, storage)
        self.baseurl      = 'https://www.egazetteharyana.gov.in/ArchiveNotifications.aspx'
        self.hostname     = 'www.egazetteharyana.gov.in'
        self.search_endp  = 'ArchiveNotifications.aspx'
        self.gazette_js   = 'window.open\(\'(?P<href>ArchiveNotifications[^\']+)'

    def get_post_data(self, tags, dateobj, category):
        datestr  = utils.dateobj_to_str(dateobj, '-', reverse = True)
        postdata = []

        radio_set = False
        for tag in tags:
            name  = None
            value = None

            if tag.name == 'input':
                name  = tag.get('name')
                value = tag.get('value')
                t     = tag.get('type')
                if t == 'image' or name == 'ctl00$ContentPlaceHolder1$archiveNotification':
                    continue
                if name == 'ctl00$ContentPlaceHolder1$RadioButtonList1' \
                        and radio_set:
                    continue
         
                if name == 'ctl00$ContentPlaceHolder1$txtstartdate' or \
                        name == 'ctl00$ContentPlaceHolder1$txtenddate':
                    value = datestr
                elif name == 'ctl00$ContentPlaceHolder1$Button1':
                    value = 'Submit'
                elif name == 'ctl00$ContentPlaceHolder1$RadioButtonList1':
                    value = '-1'
                    radio_set = True
            elif tag.name == 'select':
                name = tag.get('name')
                if name == 'BtnSearch':
                    value = 'search'
                elif name == 'ctl00$ContentPlaceHolder1$ddlGazetteCat':
                    value = category['value']
                elif name == 'ctl00$ContentPlaceHolder1$ddldepartment':
                    value = '-1'

            if name:
                if value == None:
                    value = ''
                postdata.append((name, value))
        return postdata

    def find_categories(self, d):
        cats = []
        select = d.find('select', {'id': 'ContentPlaceHolder1_ddlGazetteCat'})
        if not select:
            return cats

        for option in select.find_all('option'):
            value = option.get('value')
            if value == '-1':
                continue

            name = utils.get_tag_contents(option)
            cats.append({'value': value, 'name': name})

        return cats

    def download_oneday(self, relpath, dateobj):
        dls = []
        response = self.download_url(self.baseurl)

        if not response or not response.webpage:
            self.logger.error('Unable to download the webpage for %s', dateobj)
            return dls

        d = utils.parse_webpage(response.webpage, self.parser)
        if not d:
            self.logger.error('Unable to parse the webpage for %s', dateobj)
            return dls

        categories = self.find_categories(d)
        for category in categories:
            dls.extend(self.download_onecat(relpath, dateobj, category))

        return dls 

    def download_onecat(self, relpath, dateobj, category):
        dls = []
        cookiejar  = CookieJar()
        response = self.get_search_results(self.baseurl, dateobj, category, cookiejar)

        pagenum = 1
        while response != None and response.webpage != None:
            metainfos, nextpage = self.parse_search_results(response.webpage, \
                                                            dateobj, pagenum)
            postdata = self.get_form_data(response.webpage, dateobj, category, self.search_endp)

            relurls = self.download_metainfos(relpath, metainfos, self.baseurl,\
                                              postdata, cookiejar)
            dls.extend(relurls)
            if nextpage:
                pagenum += 1
                self.logger.info('Going to page %d for date %s', pagenum, dateobj)
                response = self.download_nextpage(nextpage, search_url, postdata, cookiejar)
            else:
                break
        return dls

    def get_form_data(self, webpage, dateobj, category, form_href):
        search_form = self.get_search_form(webpage, dateobj, form_href)
        if search_form == None:
            self.logger.warning('Unable to get the search form for day: %s', dateobj)
            return None

        reobj  = re.compile('^(input|select)$')
        inputs = search_form.find_all(reobj)
        postdata = self.get_post_data(inputs, dateobj, category)

        return postdata

    def get_search_results(self, search_url, dateobj, category, cookiejar):
        response = self.download_url(search_url, savecookies = cookiejar, loadcookies=cookiejar)

        while response and response.webpage: 
            response = self.submit_captcha_form(search_url, response.webpage, \
                                                cookiejar, dateobj, category)
             
            if not response or not response.webpage:
                break
            d = utils.parse_webpage(response.webpage, self.parser)
            if d and not self.is_form_webpage(d):
                break 
            else:    
                response = self.download_url(search_url, savecookies = cookiejar, loadcookies=cookiejar)
                
        return response
    
        
    def submit_captcha_form(self, search_url, webpage, cookiejar, \
                            dateobj, category):        
        captcha  = self.download_url(self.captcha_url, loadcookies=cookiejar)
        if captcha == None or captcha.webpage == None:
            self.logger.warning('Unable to download captcha')
            return None

        img = Image.open(io.BytesIO(captcha.webpage))
                    
        captcha_val = decode_captcha.haryana_captcha(img)

        postdata = self.get_form_data(webpage, dateobj, category, self.search_endp)
        if postdata == None:
            return None

        newpost = []
        for name, value in postdata:
            if name == 'ctl00$ContentPlaceHolder1$txtcaptcha':
                value = captcha_val
            newpost.append((name, value))   
        response = self.download_url(search_url, savecookies = cookiejar, \
                                   loadcookies = cookiejar, postdata = newpost)
        return response

    def download_metainfos(self, relpath, metainfos, search_url, \
                           postdata, cookiejar):
        dls = []
        for metainfo in metainfos:
            if 'download' not in metainfo or 'notification_num' not in metainfo:
                self.logger.warning('Required fields not present. Ignoring- %s' % metainfo) 
                continue

            href = metainfo.pop('download')
            reobj = re.search('javascript:__doPostBack\(\'(?P<event_target>[^\']+)\'', href)
            if not reobj:
                self.logger.warning('No event_target in the gazette link. Ignoring - %s' % metainfo)
                continue 

            groupdict    = reobj.groupdict()
            event_target = groupdict['event_target']

            newpost = []
            for t in postdata:
                if t[0] == '__EVENTTARGET':
                    t = (t[0], event_target)
                elif t[0] == 'ctl00$ContentPlaceHolder1$ctl03':
                    t = (t[0], '10')
                newpost.append(t)

            response = self.download_url(search_url, postdata = newpost, \
                                         loadcookies= cookiejar)
            if not response or not response.webpage:
                self.logger.warning('Could not get the page for %s' % metainfo)
                continue
            webpage = response.webpage.decode('utf-8', 'ignore') 
            reobj = re.search(self.gazette_js, webpage)
            if not reobj:
                self.logger.warning('Could not get url link for %s' % metainfo)
                continue
            href  = reobj.groupdict()['href']
            gzurl = urllib.parse.urljoin(search_url, href)

            num = metainfo['notification_num']
            if 'gztype' in metainfo:
                num = '%s_%s' % (metainfo['gztype'], num)
            num, n = re.subn('[\s/().\[\]]+', '-', num)
            relurl = os.path.join(relpath, num)

            if self.save_gazette(relurl, gzurl, metainfo):
                dls.append(relurl)

        return dls

