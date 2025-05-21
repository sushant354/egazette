import logging
import datetime
import urllib.request, urllib.parse, urllib.error
import os
import time
import requests
from requests.adapters import HTTPAdapter
from requests.packages.urllib3.util.retry import Retry

from ..utils import utils

from .datasrcs_info import get_start_date

class WebResponse:
   def __init__(self):
       self.srvresponse  = None
       self.webpage      = None
       self.error        = None
       self.response_url = None

   def set_error(self, error):
       self.error = error

   def set_webpage(self, webpage):
       self.webpage = webpage

   def set_srvresponse(self, response):
       self.srvresponse = response

   def set_response_url(self, response_url):
       self.response_url = response_url

class Downloader:
    def __init__(self, name, storage_manager):
        self.hostname    = None
        self.name        = name

        self.storage_manager = storage_manager
        self.backoff  = 0
        self.lookback = 15 
        self.num_http_retries = 3
        self.retry_delay_base_secs = 100
        self.retry_delay_max_secs = 300
        self.request_timeout_secs = 400

    
        self.logger      = logging.getLogger('crawler.%s' % self.name)

        self.useragent   = 'Mozilla/5.0 (X11; Ubuntu; Linux x86_64; rv:59.0) Gecko/20100101 Firefox/59.0'

    def all_downloads(self, event):
        start_date = get_start_date(self.name)
        assert start_date != None
        return self.sync(start_date, datetime.datetime.today(), event)

    def sync_daily(self, event):
        todate = datetime.datetime.today() #- datetime.timedelta(days = 1)
        fromdate = todate - datetime.timedelta(days = self.lookback)
        return self.sync(fromdate, todate, event)

    def sync(self, fromdate, todate, event):
        newdownloads = []
        while fromdate <= todate:
            if event.is_set():
                self.logger.warning('Exiting prematurely as timer event is set')
                break

            dateobj   = fromdate.date()
            self.logger.info('Date %s' % dateobj)

            tmprel    = os.path.join (self.name, dateobj.__str__())
            dls = self.download_oneday(tmprel, dateobj)
            self.logger.info('Got %d gazettes for day %s' % (len(dls), dateobj))
            newdownloads.extend(dls)
            fromdate += datetime.timedelta(days=1)
        return newdownloads

    def get_session_retry(self):
        retries = self.num_http_retries
        retry = Retry(
            total=retries,
            read=retries,
            connect=retries,
            #backoff_max=self.retry_delay_max_secs,
            backoff_factor=self.retry_delay_base_secs,
            status_forcelist=set([503,504,403]),
        )
        return retry

    def get_session(self):
        s = requests.session()
        retry = self.get_session_retry()
        s.mount('http://', HTTPAdapter(max_retries=retry))
        s.mount('https://', HTTPAdapter(max_retries=retry))
        return s


    def download_url_using_session(self, url, session = None, postdata = None, \
                                   referer = None, headers = {}):
        if session == None:
            session = self.get_session()

        webresponse = WebResponse()

        headers['User-agent'] = self.useragent

        if referer:
            headers['Referer'] = referer

        fixed_url = self.url_fix(url)        
        req_kwargs = { 'timeout': self.request_timeout_secs }

        try:
            if postdata == None:
                response = session.get(fixed_url, headers=headers, **req_kwargs)
            else:
                if type(postdata) == list:
                    postdata = dict(postdata)
                response = session.post(fixed_url, data=postdata, headers=headers, **req_kwargs)
            self.logger.debug('Request url: %s headers: %s data: %s', \
                              fixed_url, response.request.headers, postdata)
            status_code = response.raise_for_status()
            webresponse.set_webpage(response.content)
            webresponse.set_srvresponse({ 'headers': response.headers, 'status': response.status_code })
            webresponse.set_response_url(response.url)
        except Exception as e:
            webresponse.set_error(e)
            self.logger.warning('Could not fetch: %s error: %s' % (url, e))
            return webresponse

        self.logger.info('Url: %s response_url: %s Status: %s' % (fixed_url, response.url, status_code))
        return webresponse

    def download_url(self, url, loadcookies = None, savecookies = None, \
                     postdata = None, referer = None, \
                     encodepost= True, headers = {}):
        for i in range(0, self.num_http_retries):
            if i > 0:
                time.sleep(i * self.retry_delay_base_secs)
            response = self.download_url_onetime(url, loadcookies, savecookies,\
                                                 postdata, referer, \
                                                 encodepost, headers)
            if response.error == None:
                return response
            elif isinstance(response.error, urllib.error.HTTPError) and \
                    response.error.code not in [503, 504, 403]:
                break

            i += 1

        return None

    def download_url_onetime(self, url, loadcookies, savecookies, \
                             postdata, referer, encodepost, headers):

        webresponse = WebResponse()

        if self.backoff > 0:
            time.sleep(self.backoff)

        headers['User-agent'] = self.useragent

        if referer:
            headers['Referer'] = referer
 
        encodedData = None
        if postdata:
            if encodepost:
                encodedData = urllib.parse.urlencode(postdata).encode('utf-8')
            else:
                encodedData = postdata

        fixed_url = self.url_fix(url)        
        request = urllib.request.Request(fixed_url, encodedData, headers)

        if loadcookies != None:
            loadcookies.add_cookie_header(request)
            if 'Cookie' in request.unredirected_hdrs:
                request.headers['Cookie'] = request.unredirected_hdrs.pop('Cookie')
        self.logger.debug('Request url: %s headers: %s data: %s', \
                            request.full_url, request.headers, request.data)
        try:
            opener  = urllib.request.urlopen(request, timeout = self.request_timeout_secs)
            response = opener.info()
            webpage  = opener.read()
            
            webresponse.set_webpage(webpage)
            webresponse.set_srvresponse(response)
            webresponse.set_response_url(opener.geturl())

            self.logger.info('Url: %s response_url: %s Status: %s' % (fixed_url, opener.geturl(), opener.getcode()))
        except Exception as e:
            webresponse.set_error(e)
            self.logger.warning('Could not fetch: %s error: %s' % (url, e))
            return webresponse 

        self.logger.debug('Server response: %s', response)

        if 'Set-Cookie' in response: 
            cookie = response['Set-Cookie']
            if savecookies != None and cookie:
                savecookies.extract_cookies(opener, request)

        return webresponse

    def url_fix(self, s, charset='utf-8'):
        """Sometimes you get an URL by a user that just isn't a real
        URL because it contains unsafe characters like ' ' and so on.  This
        function can fix some of the problems in a similar way browsers
        handle data entered by the user:

        >>> url_fix(u'http://de.wikipedia.org/wiki/Elf (Begriffsklrung)')
        'http://de.wikipedia.org/wiki/Elf%20%28Begriffskl%C3%A4rung%29'

        :param charset: The target charset for the URL if the url was
                        given as unicode string.
        """
        purl = urllib.parse.urlsplit(s)
        path = urllib.parse.quote(purl.path, '/%')
        qs = urllib.parse.quote_plus(purl.query, ':&=')

        return urllib.parse.urlunsplit((purl.scheme, purl.netloc, path, \
                                        qs, purl.fragment))

class BaseGazette(Downloader):
    def __init__(self, name, storage_manager):
        Downloader.__init__(self, name, storage_manager)
        self.hostname    = None
        self.parser      = 'lxml'

    def is_valid_gazette(self, doc, min_size):
        return (min_size <= 0 or len(doc) > min_size)

    def get_file_extension(self, doc):
        mtype = utils.get_buffer_type(doc)
        return utils.get_file_extension(mtype)

    def save_gazette(self, relurl, gurl, metainfo, postdata = None, \
                     referer = None, cookiefile = None, validurl = True, \
                     min_size=0, count=0, hdrs = {}, encodepost = True):
        updated = False
        if self.storage_manager.should_download_raw(relurl, gurl, \
                                                    validurl = validurl):
            if cookiefile:
                response = self.download_url(gurl, referer = referer, \
                                 postdata = postdata, loadcookies = cookiefile,\
                                 headers = hdrs, encodepost = encodepost)
            else:
                response = self.download_url(gurl, postdata = postdata, \
                                             encodepost = encodepost, \
                                             referer = referer)

            if response == None:
                return updated
                 
            doc = response.webpage 
            if doc and self.is_valid_gazette(doc, min_size):  
                if self.storage_manager.save_rawdoc(self.name, relurl, response.srvresponse, doc):
                    updated = True
                    self.logger.info('Saved rawfile %s' % relurl)
                else:
                    self.logger.info('not able to save the doc %s' % relurl)
            else:                    
                self.logger.info('doc not downloaded %s' % relurl)
        else:
            self.logger.info('rawdoc already exists %s' % relurl)
        if validurl:
            metainfo.set_url(self.url_fix(gurl))
        if self.storage_manager.save_metainfo(self.name, relurl, metainfo): 
            updated = True
            self.logger.info('Saved metainfo %s' % relurl)
        return updated

