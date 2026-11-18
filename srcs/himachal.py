import urllib.request, urllib.parse, urllib.error
import re
import datetime
import time
import os 
import io
from PIL import Image
from http.cookiejar import CookieJar
from ..utils import utils
from ..utils import decode_captcha
from .basegazette import BaseGazette

class Himachal(BaseGazette):
    def __init__(self, name, storage):
        BaseGazette.__init__(self, name, storage)
        self.baseurl  = 'https://rajpatra.hp.gov.in/searchG.aspx'
        self.hostname = 'rajpatra.hp.gov.in'
        self.search_endp = './searchG.aspx'
        self.result_table = 'ContentPlaceHolder1_GVNotification'
        self.captcha_key = 'ctl00$ContentPlaceHolder1$txtCaptcha'
        self.gazette_key = 'ctl00$ContentPlaceHolder1$DDlistGazette'
        self.dept_key    = 'ctl00$ContentPlaceHolder1$ddlDepartment'
        self.departments = {}   # cache: department id -> name


    def find_next_page(self, tr, curr_page):
        if tr.find('table') is None:
            return None

        nextpage = None

        links = tr.findAll('a')

        if len(links) <= 0:
            return None

        lastpage = None
        for link in links:
            contents = utils.get_tag_contents(link)
            if link.get('href'):
                lastpage = {'href': link.get('href'), 'title': contents}

            try:
                val = int(contents)
            except ValueError:
                continue

            if val == curr_page + 1 and link.get('href'):
                nextpage = {'href': link.get('href'), 'title': f'{val}'}
                break

        if nextpage is None and lastpage is not None and lastpage['title'] == '...':
            nextpage = lastpage

        return nextpage



    def get_form_data(self, webpage, dateobj, form_href, gazette=None, dept=None):
        search_form = utils.get_search_form(webpage, self.parser, form_href)
        if search_form is None:
            self.logger.warning('Unable to get the search form for day: %s', dateobj)
            return None 

        reobj  = re.compile('^(input|select)$')
        inputs = search_form.find_all(reobj)
        postdata = self.get_post_data(inputs, dateobj, gazette, dept)

        return postdata

    def parse_departments(self, webpage):
        # department id -> name; the server ignores the department when a
        # gazette number is selected, so this is only a cache of the values
        d = utils.parse_webpage(webpage, self.parser)
        if d is None:
            return {}
        sel = d.find('select', {'name': self.dept_key})
        if sel is None:
            return {}
        depts = {}
        for opt in sel.find_all('option'):
            val = opt.get('value')
            if val:
                depts[val] = utils.get_tag_contents(opt).strip()
        return depts

    def parse_gazette_options(self, webpage):
        # returns [(date, option value)], e.g.
        # (date(2021,12,17), '[17/12/2021] 171/GAZETTE/2021-17/12/2021')
        d = utils.parse_webpage(webpage, self.parser)
        if d is None:
            return []
        sel = d.find('select', {'name': self.gazette_key})
        if sel is None:
            return []
        gazettes = []
        for opt in sel.find_all('option'):
            val = opt.get('value')
            reobj = re.match(r'\[(\d{2}/\d{2}/\d{4})\]', val or '')
            if not reobj:
                continue
            try:
                gzdate = datetime.datetime.strptime(reobj.group(1), '%d/%m/%Y').date()
            except ValueError:
                continue
            gazettes.append((gzdate, val))
        return gazettes

    def get_column_order(self, tr):
        order = []
        for td in tr.find_all('th'):
            txt = utils.get_tag_contents(td)
            if txt and re.search(r'Subject', txt):
                order.append('subject')
            elif txt and re.search(r'Department', txt):
                order.append('department')
            elif txt and re.search(r'Notification\s+Number', txt):
                order.append('notification_num')
            elif txt and re.search(r'Gazette\s+Number', txt):
                order.append('gazetteid')
            elif txt and re.search(r'Date', txt):
                order.append('issuedate')
            else:
                order.append('')
        return order

    def get_post_data(self, tags, dateobj, gazette=None, dept=None):
        datestr = dateobj.strftime('%d/%m/%Y')
        postdata = []

        for tag in tags:
            name  = None
            value = None

            if tag.name == 'input':
                name  = tag.get('name')
                value = tag.get('value')
                t     = tag.get('type')
                if t == 'image' or t == 'checkbox':
                    continue
                elif name == 'ctl00$ContentPlaceHolder1$txtStartDate':
                    value = datestr
                elif name == 'ctl00$ContentPlaceHolder1$txtEndDate':
                    value = datestr
            elif tag.name == 'select':
                name = tag.get('name')
                if gazette and name == self.gazette_key:
                    value = gazette
                elif dept and name == self.dept_key:
                    value = dept

            if name:
                if value is None:
                    value = ''
                postdata.append((name, value))
        return postdata

    def process_result_row(self, tr, metainfos, order):
        metainfo = utils.MetaInfo()

        i = 0
        for td in tr.find_all('td'):
            if len(order) > i:
                col = order[i]
                txt = utils.get_tag_contents(td)
                if txt:
                    txt = txt.strip()

                if col in ['department', 'notification_num', 'issuedate']:
                    metainfo[col] = txt

                elif col in ['subject', 'gazetteid']:
                    metainfo[col] = td
            i += 1

        if 'subject' in metainfo:
            metainfos.append(metainfo)

    def update_metainfo(self, field, url_field, metainfo):
        td = metainfo.pop(field)

        txt = utils.get_tag_contents(td)
        metainfo[field] = txt.strip()

        link = td.find('a')
        if link and link.get('onclick'):
            onclick = link.get('onclick')

            reobj = re.search(r'window\.open\(\'(?P<href>[^\']+)', onclick)
            if reobj:
                href  = reobj.groupdict()['href']
                metainfo[url_field] = href

    def clean_id(self, docid):
        docid = docid.strip()
        docid = docid.replace('/','_')
        docid = docid.replace(' ','_')
        return docid

    def download_metainfos(self, metainfos, search_url, dateobj, cookiejar, relpath):
        dls = []

        by_gazetteid = {}
        for metainfo in metainfos:
            self.update_metainfo('gazetteid', 'gzurl', metainfo)
            self.update_metainfo('subject', 'notification_url', metainfo)
            gazetteid = metainfo['gazetteid']
            if gazetteid not in by_gazetteid:
                by_gazetteid[gazetteid] = []
            by_gazetteid[gazetteid].append(metainfo)

        for gazetteid, metainfos in by_gazetteid.items():
            newmeta = utils.MetaInfo()

            gznum = gazetteid.split('/')[0]
            newmeta['gznum'] = gznum
            newmeta['gazetteid'] = gazetteid

            gzdate = metainfos[0]['issuedate']
            try:
                gzdate = datetime.datetime.strptime(gzdate, '%d/%m/%Y').date()
            except Exception:
                self.logger.warning('Unable to get issuedate: %s', gzdate)
                continue

            if gzdate > dateobj or gzdate < dateobj:
                continue

            newmeta.set_date(gzdate)

            newmeta['notifications'] = []
            for metainfo in metainfos:
                newmeta['notifications'].append({
                    'number'     : metainfo['notification_num'],
                    'department' : metainfo['department'],
                    'subject'    : metainfo['subject']
                })

            gzurl = metainfos[0]['gzurl']
            gzurl = urllib.parse.urljoin(search_url, gzurl)

            gzurl_parsed = urllib.parse.urlparse(gzurl)
            docid = urllib.parse.parse_qs(gzurl_parsed.query)['ID'][0]

            docid = self.clean_id(docid)
            docid = docid.lower()
            relurl  = os.path.join(relpath, docid)
            if self.save_gazette(relurl, gzurl, newmeta, cookiefile=cookiejar):
                dls.append(relurl)

        return dls


    def download_captcha(self, search_url, webpage, cookiejar):
        d = utils.parse_webpage(webpage, self.parser)
        if d is None:
            return None

        imgs = d.find_all('img')
        for img in imgs:
            src = img.get('src')
            if src and src.find('CaptchaImage.axd') >= 0:
                captcha_url = urllib.parse.urljoin(search_url, src)
                return self.download_url(captcha_url, loadcookies=cookiejar, \
                                         savecookies=cookiejar, referer=search_url)

        return None

    def solve_captcha(self, img):
        captcha_val = decode_captcha.himachal(img).strip()
        # there is either a delay check on the server or a race condition.. so the sleep is needed
        time.sleep(5)
        return captcha_val

    def submit_captcha_form(self, search_url, webpage, cookiejar, dateobj, gazette=None, dept=None):
        captcha = self.download_captcha(search_url, webpage, cookiejar)
        if captcha is None or captcha.webpage is None:
            self.logger.warning('Unable to download captcha')
            return None

        img = Image.open(io.BytesIO(captcha.webpage))

        captcha_val = self.solve_captcha(img)

        postdata = self.get_form_data(webpage, dateobj, self.search_endp, \
                                      gazette, dept)
        if postdata is None:
            return None

        newpost = utils.replace_field(postdata, self.captcha_key, captcha_val)

        response = self.download_url(search_url, savecookies = cookiejar, \
                                     loadcookies = cookiejar, postdata = newpost, \
                                     referer = search_url)
        return response


    def check_captcha_failure(self, webpage):
        d = utils.parse_webpage(webpage, self.parser)
        if not d:
            return None

        div = d.find('div', {'id': 'ContentPlaceHolder1_alertdivW'})
        if div is None:
            return False

        msg = div.find('span')
        if msg is None:
            return False

        alerttxt = utils.get_tag_contents(msg)

        if re.search(r'Verfication\s+Code\s+is\s+Incorrect', alerttxt):
            return True

        return False

    def parse_search_results(self, webpage, dateobj, curr_page):
        metainfos = []
        nextpage  = None

        d = utils.parse_webpage(webpage, self.parser)
        if not d:
            self.logger.warning('Unable to parse search result page for %s', \
                                dateobj)
            return metainfos, nextpage

        tables = d.find_all('table', {'id': self.result_table})

        if len(tables) != 1:
            self.logger.warning('Could not find the result table for %s', \
                                dateobj)
            return metainfos, nextpage

        order = None
        for tr in tables[0].find_all('tr'):
            if not order:
                order = self.get_column_order(tr)
                continue

            if nextpage is not None:
                continue

            if nextpage is None:
                nextpage = self.find_next_page(tr, curr_page)
                if nextpage is not None:
                    continue

            if tr.find('input') is None and tr.find('a') is None:
                continue

            self.process_result_row(tr, metainfos, order)

        return metainfos, nextpage


    def get_search_results(self, search_url, dateobj, cookiejar, gazette=None, dept=None):
        response = self.download_url(search_url, savecookies = cookiejar, \
                                     referer=search_url)

        while response and response.webpage:
            response = self.submit_captcha_form(search_url, response.webpage, \
                                                cookiejar, dateobj, gazette, dept)

            if not response or not response.webpage:
                self.logger.warning('Failed to post to search form for %s', \
                                    dateobj)
                return None

            has_captcha_failure = self.check_captcha_failure(response.webpage)
            if has_captcha_failure is None:
                self.logger.warning('Failed to parse search form response for %s', \
                                    dateobj)
                return None

            if not has_captcha_failure:
                break

            cookiejar.clear()
            response = self.download_url(search_url, savecookies=cookiejar, \
                                         referer=search_url)

        return response

    def download_nextpage(self, nextpage, search_url, postdata, cookiejar):
        href = nextpage.get('href') 
        if not href:
            return None

        groups = []
        for reobj in re.finditer(r"'(?P<obj>[^']+)'", href):
            groups.append(reobj.groupdict()['obj'])

        if len(groups) < 2:
            return None

        etarget = groups[0]
        page_no = groups[1]

        postdata = utils.remove_fields(postdata, set(['ctl00$ContentPlaceHolder1$btnBack',
                                                      'ctl00$ContentPlaceHolder1$BtnSendMail']))
        postdata = utils.replace_field(postdata, '__EVENTTARGET', etarget)
        postdata = utils.replace_field(postdata, '__EVENTARGUMENT', page_no)
        response = self.download_url(search_url, savecookies = cookiejar, \
                                     referer = search_url, \
                                     loadcookies = cookiejar, \
                                     postdata = postdata)

        return response 

    def parse_non_html(self, webpage):
        resp_text = webpage.decode('utf8')

        panel_label = '|updatePanel|ctl00_ContentPlaceHolder1_UdpDatePanel|'

        idx = resp_text.find(panel_label)

        str_len = int(resp_text[:idx].split('|')[-1])

        idx = idx + len(panel_label)

        end_idx = idx + str_len
        html = resp_text[idx:end_idx]

        pieces = resp_text[end_idx+1:].split('|')

        idx = 0
        base_form_data = []

        while idx < len(pieces):
            if pieces[idx] != 'hiddenField':
                idx += 1
                continue
            idx += 1
            key = pieces[idx] 
            idx += 1
            val = pieces[idx]
            base_form_data.append((key, val))
            idx += 1

        return html.encode('utf8'), base_form_data

    def sync(self, fromdate, todate, event):
        # One search per gazette number listed in the dropdown. Only the
        # gazette number is looped over, not the department: the site ignores
        # the department once a gazette number is selected and returns the
        # notifications of all departments for that gazette. Tested on
        # 171/GAZETTE/2021-17/12/2021 (departments 59, 1, 38, 7) and
        # 170/GAZETTE/2026-13/11/2026 (departments 59, 1): the rows on the
        # first page were identical for every department. So the first
        # department is used for every search, and looping over departments
        # would only repeat the same rows and the captcha solves.
        # All pages of 170/GAZETTE/2026-13/11/2026 (2 pages, 15 + 5 rows)
        # were also compared for departments 59, 1 and 38: identical rows
        # in the same order.
        response = self.download_url(self.baseurl, savecookies=CookieJar(), \
                                     referer=self.baseurl)
        if response is None or response.webpage is None:
            self.logger.warning('Unable to get the search page')
            return []

        self.departments = self.parse_departments(response.webpage)
        gazettes = self.parse_gazette_options(response.webpage)
        if not gazettes or not self.departments:
            self.logger.warning('Unable to parse the gazette number dropdown')
            return []

        dept = next(iter(self.departments))
        newdownloads = []
        for gzdate, gazette in sorted(gazettes):
            if gzdate < fromdate.date() or gzdate > todate.date():
                continue
            if event.is_set():
                self.logger.warning('Exiting prematurely as timer event is set')
                break
            self.logger.info('Gazette %s', gazette)
            tmprel = os.path.join(self.name, gzdate.__str__())
            dls = self.download_oneday(tmprel, gzdate, event, gazette, dept)
            self.logger.info('Got %d gazettes for %s' % (len(dls), gazette))
            newdownloads.extend(dls)
        return newdownloads

    def download_oneday(self, relpath, dateobj, event, gazette=None, dept=None):
        dls = []
        cookiejar = CookieJar()

        response = self.get_search_results(self.baseurl, dateobj, cookiejar, \
                                           gazette, dept)

        pagenum = 1
        all_metainfos = []
        while response is not None and response.webpage is not None:
            hidden_postdata = None

            if response.webpage.decode('utf8').find('<!DOCTYPE html>') >= 0:
                webpage  = response.webpage
                postdata = self.get_form_data(webpage, dateobj, self.search_endp, \
                                              gazette, dept)
            else:
                webpage, hidden_postdata = self.parse_non_html(response.webpage)
                for k,v in hidden_postdata:
                    postdata = utils.replace_field(postdata, k, v)


            metainfos, nextpage = self.parse_search_results(webpage, \
                                                           dateobj, pagenum)

            if event.is_set():
                self.logger.warning('Exiting prematurely as timer event is set')
                break

            all_metainfos.extend(metainfos)

            if not nextpage:
                break

            pagenum += 1
            self.logger.info('Going to page %d for date %s', pagenum, dateobj)

            response = self.download_nextpage(nextpage, self.baseurl, postdata, cookiejar)

        relurls = self.download_metainfos(all_metainfos, self.baseurl, dateobj, cookiejar, relpath)
        dls.extend(relurls)

        return dls