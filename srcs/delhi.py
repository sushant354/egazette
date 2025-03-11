import urllib.request, urllib.parse, urllib.error
import re
import os
from http.cookiejar import CookieJar

from .central import CentralBase
from ..utils import utils

class DelhiWeekly(CentralBase):
    def __init__(self, name, storage):
        CentralBase.__init__(self, name, storage)
        self.baseurl     = 'https://egazette.gov.in'

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
        response = self.download_url(curr_url, savecookies = cookiejar, \
                                     loadcookies = cookiejar, referer = curr_url, \
                                     postdata = postdata)
        if not response:
            self.logger.warning('Could not fetch %s for the day %s', curr_url, dateobj)
            return dls

        curr_url = response.response_url
        state_url = urllib.parse.urljoin(curr_url, 'StateGazette.aspx')
        response = self.download_url(state_url, savecookies = cookiejar, \
                                     loadcookies = cookiejar, referer = curr_url)
        curr_url = urllib.parse.urljoin(curr_url, 'DelhiGazette.aspx')
        response = self.download_url(curr_url, savecookies = cookiejar, \
                                    loadcookies = cookiejar, referer = state_url)

        postdata = self.get_form_data(response.webpage, dateobj, 'DelhiGazette.aspx')
        self.remove_fields(postdata, set(['Before_ePublish']))
        response = self.download_url(curr_url, savecookies = cookiejar, \
                                     loadcookies = cookiejar, referer = curr_url, \
                                     postdata = postdata)
        if not response:
            self.logger.warning('Could not fetch %s for the day %s', curr_url, dateobj)
            return dls

        state_url = curr_url
        curr_url = urllib.parse.urljoin(curr_url, 'SearchCategory.aspx')
        response = self.download_url(curr_url, savecookies = cookiejar, \
                                     loadcookies = cookiejar, referer = state_url)

        postdata = self.get_form_data(response.webpage, dateobj, \
                                     'SearchCategory.aspx')
        postdata = self.replace_field(postdata, '__EVENTTARGET', 'ddlGazetteCategory')
        response = self.download_url(curr_url, savecookies = cookiejar, \
                                     loadcookies = cookiejar, referer = curr_url, \
                                     postdata = postdata)
        postdata = self.get_form_data(response.webpage, dateobj, \
                                     'SearchCategory.aspx')
        postdata.append(('ImgSubmitDetails_Delhi.x', '76'))
        postdata.append(('ImgSubmitDetails_Delhi.y', '20'))
        response = self.download_url(curr_url, savecookies = cookiejar, \
                                     loadcookies = cookiejar, referer = curr_url, \
                                     postdata = postdata)


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

        
class DelhiExtraordinary(DelhiWeekly):
    def __init__(self, name, storage):
        DelhiWeekly.__init__(self, name, storage)
        self.gztype   = 'Extra Ordinary'


