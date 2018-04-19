from cookielib import CookieJar
import re
import os

import utils
from basegazette import BaseGazette

class Andhra(BaseGazette):
    def __init__(self, name, storage):
        BaseGazette.__init__(self, name, storage)

        self.baseurl   = 'http://apegazette.cgg.gov.in/eGazetteSearch.do'
        self.searchurl = self.baseurl
        self.hostname  = 'apegazette.cgg.gov.in'

    def get_field_order(self, tr):
        i = 0
        order  = []
        valid = False
        for th in tr.find_all('th'):
            txt = utils.get_tag_contents(th)
            if txt and re.search('gazette\s+type', txt, re.IGNORECASE):
                order.append('gztype')
            elif txt and re.search('department', txt, re.IGNORECASE):
                order.append('department')
            elif txt and re.search('abstract', txt, re.IGNORECASE):
                order.append('subject')
            elif txt and re.search('Issue\s+No', txt, re.IGNORECASE):
                order.append('gznum')
            elif txt and re.search('Notification\s+No', txt, re.IGNORECASE):
                order.append('notification_num')
            elif txt and re.search('Download', txt, re.IGNORECASE):
                order.append('download')
                valid = True
            elif txt and re.search('', txt, re.IGNORECASE):
                order.append('')

            else:
                order.append('')    

            i += 1
        if valid:    
            return order
        return None    

    def get_post_data(self, dateobj):
        datestr = utils.dateobj_to_str(dateobj, '')

        postdata = [\
            ('mode',                  'unspecified'),  \
            ('property(abstract)',    ''  ), \
            ('property(department)',  '0'), \
            ('property(docid)',       ''), \
            ('property(fromdate)',    datestr), \
            ('property(gazetteno)',   ''), \
            ('property(gazettePart)', '0'), \
            ('property(gazetteType)', '0'), \
            ('property(month1)',      '0'), \
            ('property(search)',      'search'), \
            ('property(todate)',      datestr), \
            ('property(year1)',       '0'), \
        ]
        return postdata

    def get_postdata_for_doc(self, docid, dateobj):
        postdata = [\
            ('mode',                  'viewDocument'),  \
            ('property(abstract)',    ''  ), \
            ('property(department)',  '0'), \
            ('property(docid)',       docid), \
            ('property(fromdate)',    ''), \
            ('property(gazetteno)',   ''), \
            ('property(gazettePart)', '0'), \
            ('property(gazetteType)', '0'), \
            ('property(month1)',      '0'), \
            ('property(search)',      'search'), \
            ('property(todate)',      ''), \
            ('property(year1)',       '0'), \
            ('x',                     '16'), \
            ('y',                     '16'), \
        ]
        return postdata

    def parse_search_results(self, webpage, dateobj):
        minfos = []
        d = utils.parse_webpage(webpage, self.parser)
        if not d:
            self.logger.warn('Unable to parse results page for date %s', dateobj)
            return minfos

        table = d.find('table', {'id': 'displaytable'})
        if not table:
            self.logger.warn('Unable to find result table for date %s', dateobj)
            return minfos
        
        order = None
        for tr in table.find_all('tr'):
            if not order:
                order = self.get_field_order(tr)
                continue
            metainfo = self.parse_row(tr, order, dateobj)
            if metainfo and 'download' in metainfo:
                minfos.append(metainfo)

        return minfos

    def parse_row(self, tr, order, dateobj):
        metainfo = utils.MetaInfo()
        metainfo.set_date(dateobj)

        i = 0
        for td in tr.find_all('td'):
            txt = utils.get_tag_contents(td)
            if i < len(order) and txt:
                txt = txt.strip()
                col = order[i]
                if col == 'gztype':
                    words = txt.split('/')
                    metainfo['gztype'] = words[0].strip()
                    if len(words) > 1:
                        metainfo['partnum'] = words[1].strip()
                    if len(words) > 2:
                        metainfo['district'] = words[2].strip()
                elif col == 'download':
                    inp = td.find('input')       
                    if inp and inp.get('onclick'): 
                        metainfo['download'] = inp.get('onclick')
                elif col in ['notification_num', 'gznum', 'department']:
                    metainfo[col] = txt
                elif col == 'subject':
                    metainfo.set_subject(txt)    
            i += 1
        return metainfo

    def download_oneday(self, relpath, dateobj):
        dls = []
        cookiejar  = CookieJar()
        response = self.download_url(self.baseurl, savecookies = cookiejar)
        postdata = self.get_post_data(dateobj)
        response = self.download_url(self.searchurl, postdata = postdata, \
                               loadcookies = cookiejar, savecookies = cookiejar)

        if not response or not response.webpage:
            return dls

        metainfos = self.parse_search_results(response.webpage, dateobj)
        for metainfo in metainfos:
            relurl = self.download_metainfo(metainfo, relpath, dateobj, cookiejar)
            if relurl:
                dls.append(relurl)

        return dls

    def download_metainfo(self, metainfo, relpath, dateobj, cookiejar):
        reobj = re.search('openDocument\(\'(?P<num>\d+)\'\)', metainfo['download'])        
        if not reobj:
            return None
        docid = reobj.groupdict()['num']    
        postdata = self.get_postdata_for_doc(docid, dateobj)
        metainfo.pop('download')
        relurl = os.path.join(relpath, docid)

        if self.save_gazette(relurl, self.searchurl, metainfo, \
                             cookiefile = cookiejar, \
                             postdata = postdata, validurl = False):
            return relurl
        return None    
