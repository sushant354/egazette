import re
import os
from http.cookiejar import CookieJar
import urllib.parse

import requests
from requests_toolbelt.adapters.host_header_ssl import HostHeaderSSLAdapter

from .basegazette import BaseGazette
from ..utils import utils
from ..utils.metainfo import MetaInfo


# needed because the DNS entries for the hostname is broken
# with one of the ip addresses pointing to a chinese server
# we need to force the right ip address
HOST_IP = '27.111.73.140'

class Telangana(BaseGazette):
    def __init__(self, name, storage):
        BaseGazette.__init__(self, name, storage)
        self.baseurl      = f'https://{HOST_IP}/homeAllGazetteSearch' + '?type={}'
        self.hostname     = 'tggazette.cgg.gov.in'
        self.search_endp  = 'searchGazettesNow'

    def get_field_order(self, tr):
        i = 0
        order  = []
        valid = False
        for th in tr.find_all('th'):
            txt = utils.get_tag_contents(th)
            if txt and re.search(r'gazettetype', txt, re.IGNORECASE):
                order.append('gztype')
            elif txt and re.search(r'department', txt, re.IGNORECASE):
                order.append('department')
            elif txt and re.search(r'abstract', txt, re.IGNORECASE):
                order.append('subject')
            elif txt and re.search(r'Issue\s+No', txt, re.IGNORECASE):
                order.append('gznum')
            elif txt and re.search(r'Job\s+No', txt, re.IGNORECASE):
                order.append('job_num')
            elif txt and re.search(r'Download', txt, re.IGNORECASE):
                order.append('download')
                valid = True
            elif txt and re.search(r'', txt, re.IGNORECASE):
                order.append('')

            else:
                order.append('')    

            i += 1
        if valid:    
            return order
        return None    

    def parse_row(self, tr, order, dateobj, gztype):
        metainfo = MetaInfo()
        metainfo.set_date(dateobj)
        metainfo.set_gztype(gztype)

        i = 0
        for td in tr.find_all('td'):
            txt = utils.get_tag_contents(td)
            if i < len(order) and txt:
                txt = txt.strip()
                col = order[i]
                if col == 'gztype':
                    words = txt.split('/')
                    if len(words) > 1:
                        metainfo['partnum'] = words[1].strip()
                    if len(words) > 2:
                        metainfo['district'] = words[2].strip()
                elif col == 'download':
                    link = td.find('a')       
                    if link and link.get('href'): 
                        metainfo['download'] = link.get('href')
                elif col in ['job_num', 'gznum', 'department']:
                    metainfo[col] = txt
                elif col == 'subject':
                    metainfo.set_subject(txt)    
            i += 1
        return metainfo

    def get_metainfos(self, result_table, dateobj, gztype):
        minfos = []
        order = None
        for tr in result_table.find_all('tr'):
            if not order:
                order = self.get_field_order(tr)
                continue
                
            metainfo = self.parse_row(tr, order, dateobj, gztype)
            if metainfo:
                minfos.append(metainfo)
        return minfos
 

    def get_search_form(self, webpage, endp):
        d = utils.parse_webpage(webpage, self.parser)
        if d == None:
            return None

        search_form = d.find('form', {'action': endp})
        return search_form

    def get_selected_option(self, select):
        option = select.find('option', {'selected': 'selected'})
        if option == None:
            option = select.find('option')
        if option == None:
            return ''
        val = option.get('value')
        if val == None:
            val = ''
        return val

    def replace_field(self, formdata, k, v):
        newdata = []
        for k1, v1 in formdata:
            if k1 == k:
                newdata.append((k1, v))
            else:
                newdata.append((k1, v1))
        return newdata

    def get_form_data(self, webpage, dateobj):
        search_form = self.get_search_form(webpage, self.search_endp)
        if search_form == None:
            return None 

        reobj  = re.compile('^(input|select)$')
        inputs = search_form.find_all(reobj)

        formdata = []
        for tag in inputs:
            name  = None
            value = None

            if tag.name == 'input':
                name  = tag.get('name')
                value = tag.get('value')
                t     = tag.get('type')
                if t == 'image' or t == 'submit':
                    continue
            elif tag.name == 'select':        
                name = tag.get('name')
                value = self.get_selected_option(tag)
            if name:
                if value == None:
                    value = ''
                formdata.append((name, value))

        datestr = dateobj.strftime('%Y%m%d')
        formdata = self.replace_field(formdata, 'fromDate', datestr)
        formdata = self.replace_field(formdata, 'toDate', datestr)
        return formdata


    def get_result_table(self, webpage):
        d = utils.parse_webpage(webpage, self.parser)
        if d == None:
            return None

        table = d.find('table', {'id': 'gazettesTable'})
        return table

    def download_metainfo(self, metainfo, relpath, dateobj, url):
        href = metainfo.pop('download')
        gzurl = urllib.parse.urljoin(url, href)
        gzurl = gzurl.replace(HOST_IP, self.hostname)

        docid = href.split('/')[-1]
        relurl = os.path.join(relpath, docid)
        if self.save_gazette(relurl, gzurl, metainfo):
            return relurl
        return None    

    def download_onetype(self, relpath, dateobj, gztype, typ):
        dls = []
        url = self.baseurl.format(typ)

        session = requests.session()
        session.mount('https://', HostHeaderSSLAdapter(max_retries=self.get_session_retry()))
        response = self.download_url_using_session(url, session=session, headers = { 'Host': self.hostname })
        if not response or not response.webpage:
            self.logger.warning('Unable to get %s for type %s and date %s', \
                                url, gztype, dateobj)
            return dls
        postdata = self.get_form_data(response.webpage, dateobj)
        if postdata == None:
            self.logger.warning('Unable to retreive form data for type %s and date %s', \
                                gztype, dateobj)
            return dls

        searchurl = urllib.parse.urljoin(url, self.search_endp)
        response = self.download_url_using_session(searchurl, session = session, postdata = postdata, referer = url, headers = { 'Host': self.hostname })
        if not response or not response.webpage:
            self.logger.warning('Unable to get search results at %s for type %s and date %s', \
                                searchurl, gztype, dateobj)
            return dls

        result_table = self.get_result_table(response.webpage)
        if result_table == None:
            self.logger.warning('Unable to local search table at %s for type %s and date %s', \
                                searchurl, gztype, dateobj)
            return dls

        metainfos = self.get_metainfos(result_table, dateobj, gztype)
        for metainfo in metainfos:
            relurl = self.download_metainfo(metainfo, relpath, dateobj, url)
            if relurl:
                dls.append(relurl)

        return dls

    def download_oneday(self, relpath, dateobj):
        edls = self.download_onetype(relpath, dateobj, 'Extraordinary', '1')
        odls = self.download_onetype(relpath, dateobj, 'Ordinary', '2')
        ddls = self.download_onetype(relpath, dateobj, 'District', '3')
        return edls + odls + ddls


