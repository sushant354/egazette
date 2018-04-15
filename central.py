from cookielib import CookieJar
import urllib
import re
import os

import utils
from basegazette import BaseGazette

class CentralWeekly(BaseGazette):
    def __init__(self, name, storage):
        BaseGazette.__init__(self, name, storage)
        self.baseurl     = 'http://egazette.nic.in'
        self.hostname    = 'egazette.nic.in'
        self.gztype      = 'Weekly'
        self.parser      = 'lxml'
        self.search_endp = 'Search1.aspx'
        self.result_table= 'ContentPlaceHolder1_dgGeneralUser'

    def find_search_form(self, d):
        search_form = None
        forms = d.find_all('form')
        for form in forms:
            action = form.get('action')
            if action == './%s' % self.search_endp or action == self.search_endp:
                search_form = form
                break

        return search_form

    def get_post_data(self, tags, dateobj):
        datestr  = utils.get_egz_date(dateobj)
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

                if name == 'ctl00$ContentPlaceHolder1$btnstd':
                    continue

                if name == 'ctl00$ContentPlaceHolder1$txtDateIssueF' or \
                        name == 'ctl00$ContentPlaceHolder1$txtDateIssueT':
                    value = datestr
            elif tag.name == 'select':        
                name = tag.get('name')
                if name == 'ctl00$ContentPlaceHolder1$ddlcate':
                    value = self.gztype
                elif name == 'ctl00$ContentPlaceHolder1$ddlPartSection':
                    value = 'Select Part & Section'
                elif name == 'ctl00$ContentPlaceHolder1$ddlministry':
                    value = 'Select Ministry'
                elif name == 'ctl00$ContentPlaceHolder1$ddlSubMinistry':
                    value = 'Select Department'
                elif name == 'ctl00$ContentPlaceHolder1$ddldepartment':
                    value = 'Select Office'
            if name:
                if value == None:
                    value = u''
                postdata.append((name, value))

        return postdata

    def get_search_form(self, webpage, dateobj):
        if webpage == None:
            self.logger.warn('Unable to download the starting search page for day: %s', dateobj)
            return None 

        d = utils.parse_webpage(webpage, self.parser)
        if d == None:
            self.logger.warn('Unable to parse the search page for day: %s', dateobj)
            return None

        search_form = self.find_search_form(d)
        return search_form

    def get_form_data(self, webpage, dateobj):
        search_form = self.get_search_form(webpage, dateobj)
        if search_form == None:
            self.logger.warn('Unable to get the search form for day: %s', dateobj)
            return None 

        reobj  = re.compile('^(input|select)$')
        inputs = search_form.find_all(reobj)
        postdata = self.get_post_data(inputs, dateobj)

        return postdata

    def get_search_results(self, search_url, dateobj, cookiejar):
        response = self.download_url(search_url, savecookies = cookiejar, loadcookies=cookiejar)

        postdata = self.get_form_data(response.webpage, dateobj)
        if postdata == None:
            return None

        response = self.download_url(search_url, savecookies = cookiejar, \
                                   loadcookies = cookiejar, postdata = postdata)

        postdata = self.get_form_data(response.webpage, dateobj)
        response = self.download_url(search_url, savecookies = cookiejar, \
                                   loadcookies = cookiejar, postdata = postdata)

        return response

    def get_column_order(self, tr):
        order = []
        for td in tr.find_all('td'):
            txt = utils.get_tag_contents(td)
            if txt and re.search('Ministry', txt):
                order.append('ministry')
            elif txt and re.search('Subject', txt):
                order.append('subject')
            elif txt and re.search('Download', txt):
                order.append('download')
            elif txt and re.search('Department', txt):
                order.append('department')
            elif txt and re.search('Office', txt):
                order.append('office')
            elif txt and re.search('Part.+Section', txt):
                order.append('partnum')
            elif txt and re.search('Reference', txt):
                order.append('refnum')
            else:
                order.append('')
        return order

    def parse_search_results(self, webpage, dateobj):
        metainfos = []
        d = utils.parse_webpage(webpage, self.parser)
        if not d:
            self.logger.warn('Unable to parse search result page for %s', dateobj)
            return metainfos

        tables = d.find_all('table', {'id': self.result_table})

        if len(tables) != 1:
            self.logger.warn('Could not find the result table for %s', dateobj)
            return metainfos
        
        order = None
        for tr in tables[0].find_all('tr'):
            if not order:
                order = self.get_column_order(tr)
                continue


            if tr.find('input') == None and tr.find('a') == None:
                continue

            self.process_result_row(tr, metainfos, dateobj, order)

        return metainfos

    def process_result_row(self, tr, metainfos, dateobj, order):
        metainfo = utils.MetaInfo()
        metainfos.append(metainfo)
        metainfo.set_date(dateobj)

        i = 0
        for td in tr.find_all('td'):
            if len(order) > i:
                col = order[i]
                txt = utils.get_tag_contents(td)
                if txt:
                    txt = txt.strip()

                if col == 'ministry':
                    metainfo.set_ministry(txt)
                elif col == 'subject':
                    metainfo.set_subject(txt)
                elif col == 'gztype':
                    metainfo.set_gztype(txt)    
                elif col == 'download':
                    inp = td.find('input')
                    if inp:
                        name = inp.get('name')
                        if name:
                            metainfo[col] = name
                    else:
                        link = td.find('a')
                        if link:
                            metainfo[col] = link 
                                            
                elif col in ['office', 'department', 'partnum', 'refnum']:
                    metainfo[col] = txt
            i += 1


    def download_gazette(self, relpath, search_url, postdata, \
                         metainfo, cookiejar):
        response = self.download_url(search_url, savecookies = cookiejar, \
                                     postdata = postdata, validurl = False, \
                                     loacookies = cookiejar)
        doc    = response.webpage
        srvhdr = response.srvresponse

        filename = None
        if 'Content-Disposition' in srvhdr:
            hdr   = srvhdr['Content-Disposition']
            reobj = re.search('(?P<num>\d+)\.pdf\s*$', hdr)
            if reobj:
                groups = reobj.groupdict()
                filename = groups['num']
        if filename == None:
            self.logger.warn('Could not get filename in server response for relpath: %s', relpath)
            return None

        relurl  = os.path.join(relpath, filename)
        updated = False

        if doc and  self.storage_manager.should_download_raw(relurl, None, validurl = False):
            if self.storage_manager.save_rawdoc(self.name, relurl, srvhdr, doc):
                updated = True
                self.logger.info(u'Saved rawfile %s' % relurl)

        metainfo.pop('download')
        if self.storage_manager.save_metainfo(self.name, relurl, metainfo):
            updated = True
            self.logger.info(u'Saved metainfo %s' % relurl)

        if updated:
            return relurl
        return None

    def download_oneday(self, relpath, dateobj):
        dls = []
        cookiejar  = CookieJar()
        response = self.download_url(self.baseurl, savecookies = cookiejar)
        curr_url = response.response_url
        search_url = urllib.basejoin(curr_url, self.search_endp)

        response = self.get_search_results(search_url, dateobj, cookiejar)
        if response == None or response.webpage == None:
            return dls

        metainfos = self.parse_search_results(response.webpage, dateobj)

        postdata = self.get_form_data(response.webpage, dateobj)

        return self.download_metainfos(relpath, metainfos, search_url, \
                                       postdata, cookiejar)

    def download_metainfos(self, relpath, metainfos, search_url, \
                           postdata, cookiejar):
        dls = []
        for metainfo in metainfos:
            if 'download' in metainfo:
                newpost = postdata[:]
                name = metainfo['download']
                newpost.append(('%s.x' % name, '10'))
                newpost.append(('%s.y' % name, '10'))
                relurl = self.download_gazette(relpath, search_url, newpost, metainfo, cookiejar)
                if relurl:
                    dls.append(relurl)
        return dls

class CentralExtraordinary(CentralWeekly):
    def __init__(self, name, storage):
        CentralWeekly.__init__(self, name, storage)
        self.gztype   = 'Extra Ordinary'


