from http.cookiejar import CookieJar, Cookie
import urllib.request, urllib.parse, urllib.error
import re
import os
import http.client
import datetime

from ..utils  import utils
from .central import CentralBase 

class ChattisgarhWeekly(CentralBase):
    def __init__(self, name, storage):
        CentralBase.__init__(self, name, storage)
        self.hostname     = 'egazette.cg.nic.in'
        self.baseurl      = 'https://egazette.cg.nic.in/FileSearch.aspx'
        self.search_endp  = 'FileSearch.aspx'
        self.file_url     = 'https://egazette.cg.nic.in/FileCS1.ashx?Id=%s'
        self.result_table = 'ctl00_ContentPlaceHolder2_GridView2'
        self.gztype       = '1'
        self.gznum_re     = re.compile('\u0930\u093e\u091c\u092a\u0924\u094d\u0930\s*\u0915\u094d\u0930\u092e\u093e\u0902\u0915')
        self.partnum_re   = re.compile('\s*\u092d\u093e\u0917\s+(?P<num>.+)')
        self.filenum_cookie = 'id'
        self.gazette_type = 'Ordinary'
        
    def get_post_data(self, tags, dateobj):
        datestr  = utils.dateobj_to_str(dateobj, '/')
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

                if name == 'ctl00$ContentPlaceHolder2$btnExit':
                    continue

                if name == 'ctl00$ContentPlaceHolder2$btnShow':
                    value = value.encode('utf8')

                if name == 'ctl00$ContentPlaceHolder2$DaintyDate2' or \
                        name == 'ctl00$ContentPlaceHolder2$DaintyDate1':
                    value = datestr
            elif tag.name == 'select':        
                name = tag.get('name')
                if name == 'ctl00$ContentPlaceHolder2$ddlType':
                    value = self.gztype
                if name == 'ctl00$ContentPlaceHolder2$ddldepart':
                    value = '0'
            if name:
                if value == None:
                    value = ''
                postdata.append((name, value))

        return postdata

    def get_column_order(self, tr):
        order = []
        for th in tr.find_all('th'):
            txt = utils.get_tag_contents(th)
            if txt and self.gznum_re.search(txt):
                order.append('gznum')
            elif txt and self.partnum_re.match(txt):
                reobj = self.partnum_re.match(txt)
                partnum = reobj.groupdict()['num']
                order.append('partnum|%s' % partnum)
            else:
                order.append('')    
        return order

    def process_result_row(self, tr, metainfos, dateobj, order):
        gznum = None
        i     = 0
        for td in tr.find_all('td'):
            if len(order) > i:                                            
                col = order[i]
                txt = utils.get_tag_contents(td)
                if txt:
                    txt = txt.strip()
                if col == 'gznum':
                    gznum = txt
                elif col.startswith('partnum'):
                    h, partnum = col.split('|')
                    metainfo = utils.MetaInfo()
                    metainfos.append(metainfo)
                    metainfo.set_date(dateobj)
                    metainfo.set_gztype(self.gazette_type)

                    if gznum:
                        metainfo['gznum'] = gznum
                    metainfo['partnum'] = partnum
                    inp = td.find('input')
                    if inp:
                        name = inp.get('name')
                        if name:
                            metainfo['download'] = name
            i += 1   

    def get_search_results(self, search_url, dateobj, cookiejar):
        response = self.download_url(search_url, savecookies = cookiejar, loadcookies=cookiejar)

        postdata = self.get_form_data(response.webpage, dateobj, self.search_endp)
        if postdata == None:
            return None
        response = self.download_url(search_url, savecookies = cookiejar, \
                                   loadcookies = cookiejar, postdata = postdata)
        return response

    def download_oneday(self, relpath, dateobj):
        dls = []
        cookiejar  = CookieJar()
        response = self.get_search_results(self.baseurl, dateobj, cookiejar)
        if response == None or response.webpage == None:
            return dls

        metainfos, nextpage = self.parse_search_results(response.webpage, \
                                                        dateobj, 1)
        postdata = self.get_form_data(response.webpage, dateobj, self.search_endp)
        return self.download_metainfos(relpath, metainfos, self.baseurl, \
                                       postdata, cookiejar)

    def get_relurl(self, relpath, metainfo): 
        partnum, n = re.subn('[\s()]+', '_', metainfo['partnum'])
        partnum.strip(' _')
        if 'gznum' in metainfo:
            gznum = metainfo['gznum']
        else:
            gznum = 'unkwn'    

        num     = '%s-%s' % (gznum, partnum)
        num     = num.strip(' \t\r\n_-')
        relurl = os.path.join(relpath, num)
        return relurl

    def parse_download_page(self, webpage, search_url):
        d = utils.parse_webpage(webpage, self.parser)
        if d == None:
            return None

        obj = d.find('object')
        if obj == None:
            return None
        link = obj.find('a')
        if link == None:
            return None
        url = link.get('href')
        if url == None:
            return None

        return urllib.parse.urljoin(search_url, url)


    def download_gazette(self, relpath, search_url, postdata, metainfo, cookiejar):
        relurl = self.get_relurl(relpath, metainfo)
        if not relurl:
            self.logger.warning('Not able to form relurl for %s', metainfo)
            return None

        newpost = self.remove_fields(postdata, set(['ctl00$ContentPlaceHolder2$btnShow']))

        session = self.get_session()
        session.cookies = cookiejar
        response = self.download_url_using_session(search_url, session=session, \
                                                   postdata=newpost, referer=search_url)
        if response == None or response.webpage == None:
            self.logger.warning('Unable to post to get download page for %s', relurl) 
            return None

        viewurl = response.response_url

        fileurl = self.parse_download_page(response.webpage, search_url)
        if fileurl == None:
            self.logger.warning('Unable to get fileurl for %s', relurl) 
            return None

        if self.save_gazette(relurl, fileurl, metainfo, cookiefile=cookiejar,\
                             referer=viewurl, validurl = False):
            return relurl
        return None

     
class ChattisgarhExtraordinary(ChattisgarhWeekly):
    def __init__(self, name, storage):
        ChattisgarhWeekly.__init__(self, name, storage)

        self.gztype         = '2'
        self.filenum_cookie ='id123'
        self.result_table   = 'ctl00_ContentPlaceHolder2_GridView1'
        self.file_url       = 'http://egazette.cg.nic.in/FileCS.ashx?Id=%s'
        self.gazette_type   = 'Extraordinary'

        self.notification_num_re=re.compile('\u0905\u0927\u093f\u0938\u0942\u091a\u0928\u093e\s+\u0915\u094d\u0930\u092e\u093e\u0902\u0915')
        self.notification_date_re = re.compile('\u0905\u0927\u093f\u0938\u0942\u091a\u0928\u093e\s+\u0926\u093f\u0928\u093e\u0902\u0915')
        self.subject_re = re.compile('\u0935\u093f\u0937\u092f')
        self.dept_re = re.compile('\u0935\u093f\u092d\u093e\u0917')
        self.download_re = re.compile('\u0921\u093e\u0909\u0928\u0932\u094b\u0921')

    def get_relurl(self, relpath, metainfo):
        if 'gznum' not in metainfo:
            return None
        num     = metainfo['gznum']
        relurl = os.path.join(relpath, num)
        return relurl

    def get_column_order(self, tr):
        order = []
        for th in tr.find_all('th'):
            txt = utils.get_tag_contents(th)
            if txt and self.gznum_re.search(txt):
                order.append('gznum')

            elif txt and self.subject_re.match(txt):
                order.append('subject')
            elif txt and self.dept_re.match(txt):
                order.append('department')
            elif txt and self.notification_num_re.match(txt):
                order.append('notification_num')
            elif txt and self.notification_date_re.match(txt):
                order.append('notification_date')
            elif txt and self.download_re.match(txt):
                order.append('download')
            else:
                order.append('')    
        return order

    def process_result_row(self, tr, metainfos, dateobj, order):
        metainfo = utils.MetaInfo()
        metainfo.set_gztype(self.gazette_type)
        metainfos.append(metainfo)
        metainfo.set_date(dateobj)
        i     = 0
        for td in tr.find_all('td'):
            if len(order) > i:                                            
                col = order[i]
                txt = utils.get_tag_contents(td)
                if txt:
                    txt = txt.strip()
                if col == 'subject':
                    metainfo.set_subject(txt)
                elif col  == 'gznum':
                    reobj =   re.search('\w+', txt)
                    if reobj:
                        metainfo['gznum'] = txt[reobj.start():reobj.end()] 

                elif col == 'notification_date':
                    d = utils.parse_datestr(txt)
                    if d:
                        metainfo[col] = d

                elif col in ['department', 'notification_num']:
                    metainfo[col] = txt
                elif col == 'download':
                    inp = tr.find('input')
                    if inp:
                        name = inp.get('name')
                        if name:
                            metainfo[col] = name

            i += 1
