import urllib.parse
import re
import datetime
from http.cookiejar import CookieJar

from .central import CentralBase

from ..utils import utils

class Ladakh(CentralBase):
    def __init__(self, name, storage):
        CentralBase.__init__(self, name, storage)
        self.baseurl      = 'https://egazette.ladakh.gov.in'
        self.hostname     = 'egazette.ladakh.gov.in'
        self.result_table = 'ContentPlaceHolder1_gvGazette'

    def get_column_order(self, tr):
        order = []
        for td in tr.find_all('th'):
            txt = utils.get_tag_contents(td)
            if txt and re.search(r'Ministry\s+/\s+Organization', txt):
                order.append('ministry')
            elif txt and re.search(r'Subject', txt):
                order.append('subject')
            elif txt and re.search(r'Download', txt):
                order.append('download')
            elif txt and re.search(r'Gazette\s+ID', txt):
                order.append('gazetteid')
            elif txt and re.search(r'Issue\s+Date', txt):
                order.append('issuedate')
            else:
                order.append('')
        return order

    def process_result_row(self, tr, metainfos, dateobj, order):
        metainfo = utils.MetaInfo()
        metainfos.append(metainfo)
        metainfo.set_date(dateobj)

        i  = 0
        for td in tr.find_all('td'):
            if len(order) > i:
                col = order[i]
                if col != '':
                    txt = utils.get_tag_contents(td)
                    if txt:
                        txt = txt.strip()

                    if col == 'ministry':
                        metainfo.set_ministry(txt)
                    elif col == 'subject':
                        metainfo.set_subject(txt)
                    elif col == 'issuedate':
                        metainfo['issuedate'] = datetime.datetime.strptime(txt, '%d-%b-%Y').strftime('%Y-%m-%d')
                    elif col == 'download':
                        inp = td.find('input')
                        if inp:
                            name = inp.get('name')
                            if name:
                                metainfo[col] = name
                    else:
                        metainfo[col] = txt
            i += 1



    def get_post_data(self, tags, dateobj):
        datestr  = dateobj.strftime('%d-%b-%Y')
        postdata = []

        for tag in tags:
            name  = None
            value = None

            if tag.name == 'input':
                name  = tag.get('name')
                value = tag.get('value')
                t     = tag.get('type')
                if t == 'image':
                    continue

                if name == 'ctl00$ContentPlaceHolder1$txtDateFrom' or \
                   name == 'ctl00$ContentPlaceHolder1$txtDateTo':
                    value = datestr
            elif tag.name == 'select':        
                name = tag.get('name')
            if name:
                if value is None:
                    value = ''
                postdata.append((name, value))

        return postdata

    def get_docid(self, metainfo):
        return metainfo['gazetteid']

    def download_oneday(self, relpath, dateobj):
        dls = []
        cookiejar  = CookieJar()
        response = self.download_url(self.baseurl, savecookies = cookiejar, loadcookies = cookiejar)
        if not response or not response.webpage:
            self.logger.warning('Could not fetch %s for the day %s', self.baseurl, dateobj)
            return dls

        curr_url = response.response_url
        postdata = self.get_form_data(response.webpage, dateobj, 'default.aspx')
        postdata.append(('ctl00$Img_Cross.x', 3))
        postdata.append(('ctl00$Img_Cross.y', 10))
        postdata = self.replace_field(postdata, 'ctl00$ContentPlaceHolder1$ddlkeyword', 'Select Keyword')
        response = self.download_url(curr_url, savecookies = cookiejar, \
                                     loadcookies = cookiejar, referer = curr_url, \
                                     postdata = postdata)
        if not response or not response.webpage:
            self.logger.warning('Could not fetch %s for the day %s', curr_url, dateobj)
            return dls

        curr_url = response.response_url
        search_menu_url = urllib.parse.urljoin(curr_url, 'SearchMenu.aspx')
        response = self.download_url(search_menu_url, savecookies = cookiejar, \
                                     loadcookies = cookiejar, referer = curr_url)
        if not response or not response.webpage:
            self.logger.warning('Could not fetch %s for the day %s', curr_url, dateobj)
            return dls


        curr_url = response.response_url
        form_href = curr_url.split('/')[-1]
        postdata = self.get_form_data(response.webpage, dateobj, form_href)
        postdata = self.remove_fields(postdata, set(['ctl00$ContentPlaceHolder1$btnGazetteID', \
                                                     'ctl00$ContentPlaceHolder1$btnContentID', \
                                                     'ctl00$ContentPlaceHolder1$btnMinistry', \
                                                     'ctl00$ContentPlaceHolder1$btnCategory', \
                                                     'ctl00$ContentPlaceHolder1$btnBill', \
                                                     'ctl00$ContentPlaceHolder1$btnNotification']))

        response = self.download_url(curr_url, postdata = postdata, savecookies = cookiejar, \
                                     loadcookies = cookiejar, referer = curr_url)
        if not response or not response.webpage:
            self.logger.warning('Could not fetch %s for the day %s', curr_url, dateobj)
            return dls

        curr_url = response.response_url
        form_href = curr_url.split('/')[-1]
        postdata = self.get_form_data(response.webpage, dateobj, form_href)
        postdata.append(('ctl00$ContentPlaceHolder1$ImgSubmit.x', '47'))
        postdata.append(('ctl00$ContentPlaceHolder1$ImgSubmit.y', '21'))
        response = self.download_url(curr_url, savecookies = cookiejar, \
                                     loadcookies = cookiejar, referer = curr_url, \
                                     postdata = postdata)

        pagenum = 1
        while response is not None and response.webpage is not None:
            curr_url = response.response_url
            form_href = curr_url.split('/')[-1]

            metainfos, nextpage = self.parse_search_results(response.webpage, \
                                                            dateobj, pagenum)

            postdata = self.get_form_data(response.webpage, dateobj, form_href)

            relurls = self.download_metainfos(relpath, metainfos, curr_url, \
                                              postdata, cookiejar)
            dls.extend(relurls)
            if nextpage:
                pagenum += 1
                self.logger.info('Going to page %d for date %s', pagenum, dateobj)
                response = self.download_nextpage(nextpage, curr_url, postdata, cookiejar)
            else:
                break

        return dls