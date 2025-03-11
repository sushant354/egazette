from http.cookiejar import CookieJar
import urllib.request, urllib.parse, urllib.error
import re
import os

from ..utils import utils
from .basegazette import BaseGazette
from ..utils.metainfo import MetaInfo

class CentralBase(BaseGazette):
    def __init__(self, name, storage):
        BaseGazette.__init__(self, name, storage)
        self.baseurl     = 'https://egazette.gov.in'
        self.hostname    = 'egazette.gov.in'
        self.gztype      = 'Weekly'
        self.parser      = 'lxml'
        self.search_endp = 'SearchCategory.aspx'
        self.result_table= 'tbl_Gazette'
        self.gazette_js  = 'window.open\(\'(?P<href>[^\']+)'

    def find_search_form(self, d, form_href):
        search_form = None
        forms = d.find_all('form')
        for form in forms:
            action = form.get('action')
            if action == './%s' % form_href or action == form_href:
                search_form = form
                break

        return search_form

    def get_partnum(self, select_tag):
        option = select_tag.find('option', {'selected': 'selected'})

        if option:
            val = option.get('value')
            if val:
                return val
        return ''        

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
                if t == 'image' or name == 'btnStandard' or name == 'btn_Reforms' or name == 'btnHindi':
                    continue

                if name == 'txtDateFrom' or name == 'txtDateTo':
                    value = datestr
                elif name == 'btnDetail':
                    value = 'Detailed Report'
            elif tag.name == 'select':        
                name = tag.get('name')
                if name == 'ddlGazetteCategory':
                    value = self.gztype
                elif name == 'ddlPartSection':
                    value = self.get_partnum(tag) 
                elif name == 'ddlMinistry':
                    value = 'Select Ministry'
                elif name == 'ddlDepartment':
                    value = 'Select Department'
                elif name == 'ddlOffice':
                    value = 'Select Office'
            if name:
                if value == None:
                    value = ''
                postdata.append((name, value))

        return postdata

    def get_search_form(self, webpage, dateobj, form_href):
        if webpage == None:
            self.logger.warning('Unable to download the starting search page for day: %s', dateobj)
            return None 

        d = utils.parse_webpage(webpage, self.parser)
        if d == None:
            self.logger.warning('Unable to parse the search page for day: %s', dateobj)
            return None

        search_form = self.find_search_form(d, form_href)
        return search_form

    def get_form_data(self, webpage, dateobj, form_href):
        search_form = self.get_search_form(webpage, dateobj, form_href)
        if search_form == None:
            self.logger.warning('Unable to get the search form for day: %s', dateobj)
            return None 

        reobj  = re.compile('^(input|select)$')
        inputs = search_form.find_all(reobj)
        postdata = self.get_post_data(inputs, dateobj)

        return postdata

    def get_search_results(self, search_url, dateobj, cookiejar):
        referer_url = urllib.parse.urljoin(search_url, 'SearchMenu.aspx')
        response = self.download_url(search_url, savecookies = cookiejar, loadcookies=cookiejar, referer = referer_url)

        postdata = self.get_form_data(response.webpage, dateobj, self.search_endp)
        if postdata == None:
            return None

        response = self.download_url(search_url, savecookies = cookiejar, \
                                     referer = search_url, \
                                   loadcookies = cookiejar, postdata = postdata)
        postdata = self.get_form_data(response.webpage, dateobj, self.search_endp)

        response = self.download_url(search_url, savecookies = cookiejar, \
                                     referer = search_url, \
                                  loadcookies = cookiejar, postdata = postdata)

        return response

    def get_column_order(self, tr):
        order = []
        for td in tr.find_all('th'):
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
            elif txt and re.search('(Gazette\s+ID)|(UGID)', txt):
                order.append('gazetteid')
            elif txt and re.search('Issue\s+Date', txt):
                order.append('issuedate')
            else:
                order.append('')
        return order

    def parse_search_results(self, webpage, dateobj, curr_page):
        metainfos = []
        nextpage  = None

        d = utils.parse_webpage(webpage, self.parser)
        if not d:
            self.logger.warning('Unable to parse search result page for %s', dateobj)
            return metainfos, nextpage

        tables = d.find_all('table', {'id': self.result_table})

        if len(tables) != 1:
            self.logger.warning('Could not find the result table for %s', dateobj)
            return metainfos, nextpage
        
        order = None
        for tr in tables[0].find_all('tr'):
            if not order:
                order = self.get_column_order(tr)
                continue

            if nextpage == None:
                nextpage = self.find_next_page(tr, curr_page)
                if nextpage != None:
                    continue

            if tr.find('input') == None and tr.find('a') == None:
                continue

            self.process_result_row(tr, metainfos, dateobj, order)

        return metainfos, nextpage

    def find_next_page(self, tr, curr_page):
        classes = tr.get('class')
        if classes and 'pager' in classes:
            for td in tr.find_all('td'):
                link = td.find('a')
                txt = utils.get_tag_contents(td)
                if txt:
                   try: 
                       page_no = int(txt)
                   except:
                       page_no = None
                   if page_no == curr_page + 1 and link:
                       return link

        return None               

    def download_nextpage(self, nextpage, search_url, postdata, cookiejar):
        newdata = []
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
            
        for k, v in postdata:
            if k == '__EVENTTARGET':
                newdata.append((k, etarget))
            elif k == '__EVENTARGUMENT':
                newdata.append((k, page_no))
            elif k in ['btnDetail', 'btnSubmit']:
                continue
            else:
                newdata.append((k, v))
        response = self.download_url(search_url, savecookies = cookiejar, \
                                     referer = search_url, \
                                     loadcookies = cookiejar, \
                                     postdata = newdata)
            
        return response 

    def process_result_row(self, tr, metainfos, dateobj, order):
        metainfo = MetaInfo()
        metainfos.append(metainfo)
        metainfo.set_date(dateobj)

        i        = 0
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
                                            
                elif col in ['office', 'department', 'gazetteid']:
                    metainfo[col] = txt
            i += 1


    def download_gazette(self, relpath, search_url, postdata, \
                         metainfo, cookiejar):

        if 'gazetteid' not in metainfo:
            return None

        response = self.download_url(search_url, postdata = postdata, \
                                         loadcookies= cookiejar)
        if not response or not response.webpage:
            self.logger.warning('Could not get the page for %s' % metainfo)
            return None

        webpage = response.webpage.decode('utf-8', 'ignore')
        reobj = re.search(self.gazette_js, webpage)
        if not reobj:
            self.logger.warning('Could not get url link for %s' % metainfo)
            return None

        href  = reobj.groupdict()['href']
        pdfviewer_url = urllib.parse.urljoin(search_url, href)

        response = self.download_url(pdfviewer_url, loadcookies= cookiejar)
        if not response or not response.webpage:
            self.logger.warning('Could not get the pdfviewer page for %s' % metainfo)
            return None

        d = utils.parse_webpage(response.webpage, self.parser)
        if not d:
            self.logger.warning('Could not get parse pdf view page for %s' % metainfo)
            return None

        iframe = d.find('iframe', {'id': 'framePDFDisplay'})
        if not iframe:
            self.logger.warning('Unable to find iframe with gazette link %s', metainfo)
            return None

        srcurl = iframe.get('src')
        gzurl = urllib.parse.urljoin(self.baseurl, srcurl)

        gazetteid = metainfo['gazetteid']
        reobj = re.search('(?P<num>\d+)\s*$', gazetteid)
        if not reobj:
            reobj = re.search('\(\s*(?P<num>\d+)\s*\)\s*$', gazetteid)
            if not reobj:
                return None

        filename = reobj.groupdict()['num']
        relurl   = os.path.join(relpath, filename)

        if self.save_gazette(relurl, gzurl, metainfo): 
            return relurl

        return None    

    def replace_field(self, postdata, field_name, field_value):
        newdata = []
        for k, v in postdata:
            if k == field_name:
                newdata.append((field_name, field_value))
            else:
                newdata.append((k, v))
        return newdata

    def remove_fields(self, postdata, fields):
        newdata = []
        for k, v in postdata:
            if k not in fields:
                newdata.append((k, v))
        return newdata


    def download_oneday(self, relpath, dateobj):
        dls = []
        cookiejar  = CookieJar()
        response = self.download_url(self.baseurl, savecookies = cookiejar, loadcookies = cookiejar)
        if not response:
            self.logger.warning('Could not fetch %s for the day %s', self.baseurl, dateobj)
            return dls

        curr_url = response.response_url
        postdata = self.get_form_data(response.webpage, dateobj, self.search_endp)
        search_url = urllib.parse.urljoin(curr_url, self.search_endp)

        response = self.get_search_results(search_url, dateobj, cookiejar)

        pagenum = 1
        while response != None and response.webpage != None:
            metainfos, nextpage = self.parse_search_results(response.webpage, \
                                                            dateobj, pagenum)

            postdata = self.get_form_data(response.webpage, dateobj, self.search_endp)

            relurls = self.download_metainfos(relpath, metainfos, search_url, \
                                              postdata, cookiejar)
            dls.extend(relurls)
            if nextpage:
                pagenum += 1
                self.logger.info('Going to page %d for date %s', pagenum, dateobj)
                response = self.download_nextpage(nextpage, search_url, postdata, cookiejar)
            else:
                break
 
        return dls

    def download_metainfos(self, relpath, metainfos, search_url, \
                           postdata, cookiejar):
        dls = []
        for metainfo in metainfos:
            if 'download' in metainfo:
                newpost = postdata[:]
                name = metainfo.pop('download')
                newpost.append(('%s.x' % name, '10'))
                newpost.append(('%s.y' % name, '10'))
                relurl = self.download_gazette(relpath, search_url, newpost, metainfo, cookiejar)
                if relurl:
                    dls.append(relurl)
        return dls

class CentralWeekly(CentralBase):
    def __init__(self, name, storage):
        CentralBase.__init__(self, name, storage)


    def modify_partnum(self, postdata, partnum):
        newdata = []
        for k, v in postdata:
            if k == 'ddlPartSection':
                v = partnum 
            newdata.append((k, v))
        return newdata

    def download_oneday(self, relpath, dateobj):
        dls = []
        cookiejar  = CookieJar()
        postdata = None
        while postdata == None:
            response = self.download_url(self.baseurl, savecookies = cookiejar, loadcookies = cookiejar)
            if not response:
                self.logger.warning('Could not fetch %s for the day %s', self.baseurl, dateobj)
                return dls

            curr_url = response.response_url
            postdata = self.get_form_data(response.webpage, dateobj, 'default.aspx')
        postdata.append(('ImgMessage_OK.x', 60))
        postdata.append(('ImgMessage_OK.y', 21))
        response = self.download_url(curr_url, savecookies = cookiejar, loadcookies=cookiejar, referer = curr_url, postdata = postdata)

        postdata = self.get_form_data(response.webpage, dateobj, 'default.aspx')
        postdata = self.replace_field(postdata, '__EVENTTARGET', 'sgzt')
        postdata =self.replace_field(postdata, 'ddlkeyword', 'Select Keyword')
        response = self.download_url(curr_url, savecookies = cookiejar, loadcookies=cookiejar, referer = curr_url, postdata = postdata)

        if not response or not response.webpage:
            self.logger.warning('Could not fetch %s for the day %s', search_url, dateobj)
            return dls

        curr_url = response.response_url
        postdata = self.get_form_data(response.webpage, dateobj, 'SearchMenu.aspx')
        if postdata == None:
            return None

        postdata = self.remove_fields(postdata, set(['btnGazetteID', 'btnContentID', 'btnMinistry', 'btnBill', 'btnNotification', 'btnPublish', 'btneSearch']))

        response = self.download_url(curr_url, savecookies = cookiejar, \
                                     referer = curr_url, \
                                   loadcookies = cookiejar, postdata = postdata)           
        curr_url = response.response_url
        form_href = curr_url.split('/')[-1]
        postdata = self.get_form_data(response.webpage, dateobj, form_href)
        postdata = self.replace_field(postdata, '__EVENTTARGET', 'ddlGazetteCategory')
        response = self.download_url(curr_url, savecookies = cookiejar, \
                                     referer = curr_url, \
                                   loadcookies = cookiejar, postdata = postdata)           
        curr_url = response.response_url
        form_href = curr_url.split('/')[-1]
        postdata = self.get_form_data(response.webpage, dateobj, form_href)
        postdata.append(('ImgSubmitDetails.x', '63'))
        postdata.append(('ImgSubmitDetails.y', '22'))
        response = self.download_url(curr_url, savecookies = cookiejar, \
                                     referer = curr_url, \
                                   loadcookies = cookiejar, postdata = postdata)           
        pagenum = 1
        while response != None and response.webpage != None:
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

class CentralExtraordinary(CentralWeekly):
    def __init__(self, name, storage):
        CentralWeekly.__init__(self, name, storage)
        self.gztype   = 'Extra Ordinary'


