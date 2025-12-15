import re
import os
import urllib.parse
import datetime
from http.cookiejar import CookieJar

from ..utils import utils
from .basegazette import BaseGazette


class Chandigarh(BaseGazette):
    def __init__(self, name, storage):
        BaseGazette.__init__(self, name, storage)
        self.baseurl  = 'https://egazette.chd.gov.in/'
        self.hostname = 'egazette.chd.gov.in'
        self.gazette_select_name = 'ctl00$ContentPlaceHolder1$DDlistGazette'
        self.page_cache = {}

    def download_url_cached(self, url):

        if url not in self.page_cache:
            response = self.download_url(url)

            self.page_cache[url] = response

        return self.page_cache[url]
 
    def get_post_data(self, tags):
        postdata = []

        for tag in tags:
            name  = None
            value = None

            if tag.name == 'input':
                name  = tag.get('name')
                value = tag.get('value')
                t     = tag.get('type')
                if t in ['image', 'submit', 'checkbox']:
                    continue
            elif tag.name == 'select':
                name  = tag.get('name')
                value = utils.get_selected_option(tag)
            if name:
                if value is None:
                    value = ''
                postdata.append((name, value))

        return postdata
 
    def get_search_form(self, webpage, dateobj):
        d = utils.parse_webpage(webpage, self.parser)
        if d is None:
            self.logger.warning('Unable to parse webpage for date: %s', dateobj)
            return None

        search_form = d.find('form', { 'action': './' })
        if search_form is None:
            self.logger.warning('Unable to get the search form for date: %s', dateobj)
            return None

        return search_form


    def get_form_data(self, webpage, dateobj):

        search_form = self.get_search_form(webpage, dateobj)
        if search_form is None:
            return None

        reobj  = re.compile('^(input|select)$')
        inputs = search_form.find_all(reobj)
        postdata = self.get_post_data(inputs)
        postdata.append(('ContentPlaceHolder1_GridView1_length', '10'))

        return postdata

    def get_column_order_curryear(self, tr):
        order = []

        for td in tr.find_all('th'):
            txt = utils.get_tag_contents(td)

            if txt and re.search(r'Subject', txt):
                order.append('subject')

            elif txt and re.search(r'Department', txt):
                order.append('department')

            elif txt and re.search(r'Notification\s+No', txt):
                order.append('notification_num')

            elif txt and re.search(r'Gazette\s+No', txt):
                order.append('gazetteid')

            elif txt and re.search(r'Notification\s+Date', txt):
                order.append('issuedate')

            elif txt and re.search(r'Category', txt):
                order.append('category')

            elif txt and re.search(r'Action', txt):
                order.append('download')

            else:
                order.append('')
        return order

    def get_column_order_prevyear(self, tr):
        order = []

        for td in tr.find_all('th'):
            txt = utils.get_tag_contents(td)

            if txt and re.search(r'Subject', txt):
                order.append('subject')

            elif txt and re.search(r'Department', txt):
                order.append('department')

            elif txt and re.search(r'Notification\s+No', txt):
                order.append('notification_num')

            elif txt and re.search(r'Gazette\s+No', txt):
                order.append('gazetteid')

            elif txt and re.search(r'Date', txt):
                order.append('issuedate')

            else:
                order.append('')
        return order


    def process_row_curryear(self, tr, order): 
        metainfo = utils.MetaInfo()

        i = 0
        for td in tr.find_all('td'):
            if len(order) > i:
                col = order[i]
                txt = utils.get_tag_contents(td)
                if txt:
                    txt = txt.strip()

                if col == 'download':
                    metainfo[col] = td
                elif col != '':
                    metainfo[col] = txt
            i += 1

        return metainfo

    def process_row_prevyear(self, tr, order): 
        metainfo = utils.MetaInfo()

        i = 0
        for td in tr.find_all('td'):
            if len(order) > i:
                col = order[i]
                txt = utils.get_tag_contents(td)
                if txt:
                    txt = txt.strip()

                if col == 'subject':
                    metainfo[col] = td
                elif col == 'gazetteid':
                    metainfo[col] = td
                elif col != '':
                    metainfo[col] = txt
            i += 1

        return metainfo


    def get_results_table(self, webpage, dateobj, result_table_id):
        d = utils.parse_webpage(webpage, self.parser)
        if d is None:
            self.log.warning('Unable to parse results page for date: %s', dateobj)
            return None
 
        results_table = d.find('table', {'id': result_table_id})
        if results_table is None:
            self.logger.warning('Unable to find results table for date: %s', dateobj)
            return None

        return results_table

    def parse_results(self, webpage, dateobj, get_column_order, process_row, result_table_id):
        metainfos = []

        results_table = self.get_results_table(webpage, dateobj, result_table_id)
        if results_table is None:
            return metainfos

        order = None
        for tr in results_table.find_all('tr'):
            if order is None:
                order = get_column_order(tr)
                continue

            metainfo = process_row(tr, order)
            metainfos.append(metainfo)

        return metainfos

    def update_metainfo(self, metainfo, field, url_field):
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


    def download_metainfos_prevyear(self, metainfos, relpath, dateobj):
        relurls = []

        if len(metainfos) == 0:
            return relurls

        newmeta = utils.MetaInfo()
        newmeta.set_date(dateobj)
        newmeta['notifications'] = []
        for metainfo in metainfos:
            self.update_metainfo(metainfo, 'subject', 'notification_url')
            self.update_metainfo(metainfo, 'gazetteid', 'gzurl')
            newmeta['notifications'].append({
                'number'     : metainfo['notification_num'],
                'department' : metainfo['department'],
            })

        gazetteid = metainfos[0]['gazetteid']
        gznum = gazetteid.split('/')[0]
        newmeta['gazetteid'] = gazetteid
        newmeta['gznum']     = gznum
        gzurl = metainfos[0]['notification_url']
        gzurl = urllib.parse.urljoin(self.baseurl, gzurl)

        docid = gazetteid
        docid = docid.strip()
        docid = docid.replace('/','_')
        docid = docid.replace(' ','_')
        docid = docid.lower()

        relurl  = os.path.join(relpath, docid)

        if self.save_gazette(relurl, gzurl, newmeta): 
            relurls.append(relurl)

        return relurls


    def download_metainfos(self, metainfos, relpath, dateobj, postdata, cookiejar):
        relurls = []

        by_gazette_id = {}
        for metainfo in metainfos:
            gazetteid = metainfo['gazetteid']
            if gazetteid not in by_gazette_id:
                by_gazette_id[gazetteid] = []
            by_gazette_id[gazetteid].append(metainfo)

        for gazetteid, metainfos in by_gazette_id.items():
            gzdate = datetime.datetime \
                             .strptime(gazetteid.split('-')[-1], '%d/%m/%Y') \
                             .date()

            if gzdate != dateobj:
                continue

            newmeta = utils.MetaInfo()
            newmeta.set_date(gzdate)
            newmeta['gazetteid']     = metainfos[0]['gazetteid']
            newmeta['notifications'] = []
            for metainfo in metainfos:
                newmeta['notifications'].append({
                    'number'     : metainfo['notification_num'],
                    'department' : metainfo['department'],
                    'category'   : metainfo['category'],
                    'date'       : datetime.datetime \
                                           .strptime(metainfo['issuedate'], '%d/%m/%Y') \
                                           .strftime('%Y-%m-%d'),
                })

            # TODO: downloading part needs to be specialized for prev year?
            download = metainfos[0].pop('download')
            inp = download.find('input')
            if inp is None:
                self.logger.warning('Unable to find download button for {}', metainfos[0])
                continue

            newpost = []
            newpost.extend(postdata)
            newpost.append((inp.get('name'), inp.get('value')))

            gznum = gazetteid.split('/')[0]
            newmeta['gznum'] = gznum

            docid = gazetteid
            docid = docid.strip()
            docid = docid.replace('/','_')
            docid = docid.replace(' ','_')
            docid = docid.lower()


            relurl  = os.path.join(relpath, docid)

            if self.save_gazette(relurl, self.baseurl, newmeta, postdata = newpost, \
                                 cookiefile = cookiejar, referer = self.baseurl, \
                                 validurl = False):
                relurls.append(relurl)

        return relurls

    def find_gazette_id(self, webpage, dateobj):
        datestr = dateobj.strftime('%d/%m/%Y')

        search_form = self.get_search_form(webpage, dateobj)
        if search_form is None:
            return None

        select = search_form.find('select', { 'name': self.gazette_select_name })
        if select is None:
            self.logger.warning('Unable to find gazetteid list for date: %s', dateobj)
            return None

        
        options = select.find_all('option')
        for option in options:
            gazetteid = option.get('value')
            if gazetteid is None:
                continue

            if gazetteid.endswith(datestr):
                return gazetteid

        return None

    def filter_by_gazette_id(self, metainfos, dateobj):
        datestr = dateobj.strftime('%d/%m/%Y')

        curr_metainfos = []

        for metainfo in metainfos:
            if metainfo['gazetteid'].endswith(datestr):
                curr_metainfos.append(metainfo)

        return curr_metainfos


    def download_oneday(self, relpath, dateobj):
        dls = []

        response = self.download_url_cached(self.baseurl)
        if response is None or response.webpage is None:
            self.logger.warning('Unable to get main page for date: %s', dateobj)
            return dls

        gazetteid = self.find_gazette_id(response.webpage, dateobj)
        if gazetteid is None:
            return dls

        cookiejar = CookieJar()

        response = self.download_url(self.baseurl, savecookies=cookiejar)
        if response is None or response.webpage is None:
            self.logger.warning('Unable to get main page for date: %s', dateobj)
            return dls

        metainfos = self.parse_results(response.webpage, dateobj, \
                                       self.get_column_order_curryear, \
                                       self.process_row_curryear, \
                                       'ContentPlaceHolder1_GridView1')

        metainfos = self.filter_by_gazette_id(metainfos, dateobj)

        if len(metainfos) > 0:
            postdata = self.get_form_data(response.webpage, dateobj)
            relurls  = self.download_metainfos(metainfos, relpath, dateobj, postdata, cookiejar)

        else:
            
            captcha_val = 'dummy'
            datestr     = dateobj.strftime('%m/%d/%Y')
            postdata = self.get_form_data(response.webpage, dateobj)
            if postdata is None:
                return None

            postdata = self.get_form_data(response.webpage, dateobj)

            postdata = utils.replace_field(postdata, self.gazette_select_name, gazetteid)
            postdata = utils.replace_field(postdata, 'ctl00$ContentPlaceHolder1$txtfromDate4', datestr)
            postdata = utils.replace_field(postdata, 'ctl00$ContentPlaceHolder1$txtToDate4', datestr)
            postdata = utils.replace_field(postdata, 'ctl00$ContentPlaceHolder1$txtsearch4', captcha_val)
            postdata.append(('ctl00$ContentPlaceHolder1$btnSearch5', 'Search'))

            response = self.download_url(self.baseurl, postdata = postdata, \
                                         savecookies = cookiejar, loadcookies = cookiejar, \
                                         referer = self.baseurl)
            if response is None or response.webpage is None:
                self.logger.warning('Unable to get results for date: %s', dateobj)
                return dls

            metainfos = self.parse_results(response.webpage, dateobj, \
                                           self.get_column_order_prevyear, \
                                           self.process_row_prevyear, \
                                           'ContentPlaceHolder1_GridView2')

            relurls = self.download_metainfos_prevyear(metainfos, relpath, dateobj)

        dls.extend(relurls)

        return dls
