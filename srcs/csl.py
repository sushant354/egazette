import datetime
import urllib.request, urllib.parse, urllib.error
from http.cookiejar import CookieJar
import os
import re

from .central import CentralBase
from ..utils import utils
from ..utils.metainfo import MetaInfo

class CSLWeekly(CentralBase):
    def __init__(self, name, storage):
        CentralBase.__init__(self, name, storage)
        self.baseurl     = 'http://www.egazette.nic.in/Digital.aspx'
        self.search_endp = 'Digital.aspx'
        self.result_table = 'GV_Content_Detail'
        self.gazette_js   = 'window.open\(\'(?P<href>[^\']+)'
        self.partnum      = '30'


    def get_post_data(self, tags, dateobj):
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

                if name == 'btnSubmit':
                    value = 'Submit' 

            elif tag.name == 'select':        
                name = tag.get('name')
                if name == 'ddlYear':
                    value = '%d' % dateobj.year
                elif name == 'ddlCategory':
                    value = self.gztype
                elif name == 'ddlPartSection':
                    value = self.partnum
            if name:
                if value == None:
                    value = ''
                postdata.append((name, value))

        return postdata

    def get_category_postdata(self, postdata):
        newdata = []
        for k, v in postdata:
            if k == '__EVENTTARGET':
                v = 'ddlCategory'
            elif k == 'ddlPartSection':
                v = 'Select Part & Section'
            elif k == 'ddlYear':
                v = '2020'
            newdata.append((k, v))
        return newdata

    def get_part_postdata(self, postdata):
        newdata = []
        for k, v in postdata:
            if k == '__EVENTTARGET':
                v = 'ddlPartSection'
            elif k == 'ddlYear':
                v = '2020'
            newdata.append((k, v))
        return newdata

    def get_search_results(self, search_url, dateobj, cookiejar):
        response = self.download_url(search_url, savecookies = cookiejar, loadcookies=cookiejar)

        postdata = self.get_form_data(response.webpage, dateobj)
        if postdata == None:
            return None

        postdata = self.get_category_postdata(postdata)
        response = self.download_url(search_url, savecookies = cookiejar, \
                                     referer = search_url, \
                                   loadcookies = cookiejar, postdata = postdata)

        postdata = self.get_form_data(response.webpage, dateobj)
        postdata = self.get_part_postdata(postdata)

        response = self.download_url(search_url, savecookies = cookiejar, \
                                     referer = search_url, \
                                  loadcookies = cookiejar, postdata = postdata)

        postdata = self.get_form_data(response.webpage, dateobj)
        response = self.download_url(search_url, savecookies = cookiejar, \
                                     referer = search_url, \
                                  loadcookies = cookiejar, postdata = postdata)

        postdata = self.get_form_data(response.webpage, dateobj)
        response = self.download_url(search_url, savecookies = cookiejar, \
                                     referer = search_url, \
                                  loadcookies = cookiejar, postdata = postdata)

        return response


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
        dls = []
        cookiejar  = CookieJar()
        response = self.download_url(self.baseurl, savecookies = cookiejar, loadcookies = cookiejar)
        if not response:
            self.logger.warning('Could not fetch %s for the day %s', self.baseurl, dateobj)
            return dls
        curr_url = response.response_url
        search_url = urllib.parse.urljoin(curr_url, self.search_endp)
        response = self.get_search_results(search_url, fromdate, cookiejar)

        pagenum = 1
        while response != None and response.webpage != None:
            metainfos, nextpage = self.parse_search_results(response.webpage, \
                                                            fromdate, pagenum)

            metainfos = self.filter_by_date(metainfos, fromdate, todate)

            postdata = self.get_form_data(response.webpage, fromdate)

            relurls = self.download_metainfos(relpath, metainfos, search_url, \
                                              postdata, cookiejar)
            dls.extend(relurls)
            if nextpage:
                pagenum += 1
                self.logger.info('Going to page %d for date %s', pagenum, fromdate)

                response = self.download_nextpage(nextpage, search_url, postdata, cookiejar)
            else:
                break

        return dls

    def download_gazette(self, relpath, search_url, postdata, \
                         metainfo, cookiejar):

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
        gzurl = urllib.parse.urljoin(search_url, href)

        reobj = re.search('(?P<gzid>[^/]+).pdf$', href)
        if not reobj:
            self.logger.warning('Could not get gazette id in %s' % href)
            return None

        gzid = reobj.groupdict()['gzid']
        metainfo['gazetteid'] = gzid

        relurl = os.path.join(relpath, metainfo.get_date().__str__(), gzid)

        if self.save_gazette(relurl, gzurl, metainfo):
            return relurl

        return None

    def filter_by_date(self, metainfos, fromdate, todate):
        minfos = []
        for metainfo in metainfos:
            dateobj = metainfo.get_date()
            if dateobj and dateobj >= fromdate and dateobj <= todate:
                minfos.append(metainfo)
        return minfos

    def process_result_row(self, tr, metainfos, dateobj, order):
        metainfo = MetaInfo()
        metainfos.append(metainfo)
        metainfo.set_gztype(self.gztype)

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

                elif col == 'gazetteid':
                    metainfo[col] = txt
                elif col == 'issuedate':
                    dateobj = None
                    try: 
                        dateobj = utils.to_dateobj(txt)
                    except:
                        self.logger.warning('Unable to get date from %s', txt)
                    if dateobj:
                        metainfo.set_date(dateobj)
            i += 1

    def find_next_page(self, tr, curr_page):
        classes = tr.get('class')
        if classes and 'pager' in classes:
            prev_page = None
            for td in tr.find_all('td'):
                link = td.find('a')
                txt = utils.get_tag_contents(td)
                if txt:
                   txt = txt.strip()
                   self.logger.debug('%s %s %s', txt, curr_page, link)

                   if txt == '...' and curr_page % 10 == 0 and link \
                           and prev_page == curr_page:
                       return link

                   try: 
                       page_no = int(txt)
                       prev_page = page_no
                   except:
                       page_no = None
                   if page_no == curr_page + 1 and link:
                       return link

        return None               

class CSLExtraordinary(CSLWeekly):
    def __init__(self, name, storage):
        CSLWeekly.__init__(self, name, storage)
        self.gztype   = 'Extra Ordinary'
        self.partnum  = '31'


