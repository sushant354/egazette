import re
import os
import datetime

import utils
from central import CentralWeekly

class Bihar(CentralWeekly):
    def __init__(self, name, storage):
        CentralWeekly.__init__(self, name, storage)
        self.hostname   = 'egazette.bih.nic.in'
        self.baseurl    = 'http://egazette.bih.nic.in/SearchGazette.aspx'
        self.search_endp = 'SearchGazette.aspx'
        self.result_table = 'ctl00_ContentPlaceHolder1_DetailView'
        self.start_date   = datetime.datetime(2008, 9, 24)

    def get_post_data(self, tags, dateobj):
        datestr  = utils.dateobj_to_str(dateobj, '/')
        postdata = []
        gztype   = None
        for tag in tags:
            name   = None
            value  = None
            if tag.name == 'input':
                name  = tag.get('name')
                value = tag.get('value')
                t     = tag.get('type')
                if t == 'image' or name in ['ctl00$ContentPlaceHolder1$TxtGazetteNo', 'ctl00$ContentPlaceHolder1$BtnCancel']:
                    continue
                if name == 'ctl00$ContentPlaceHolder1$TYPE':
                    if gztype != None:
                        continue
                    else:
                        value  = 'RadioButton1'
                        gztype = value
                            
                if name == 'ctl00$ContentPlaceHolder1$BtnSearch':
                    value = 'Search' 

                if name == 'ctl00$ContentPlaceHolder1$CheckBoxYearAll':
                    value = 'on'

                if name == 'ctl00$ContentPlaceHolder1$TextBox2' or name == 'ctl00$ContentPlaceHolder1$TextBox1':
                    value = datestr

            elif tag.name == 'select':        
                name = tag.get('name')
                if name in ['ctl00$ContentPlaceHolder1$ddlYear']:
                    continue
                if name == 'ctl00$ContentPlaceHolder1$ddlFilter':
                    value = '1'

            if name:
                if value == None:
                    value = u''
                postdata.append((name, value))

        return postdata

    def get_column_order(self, tr):
        order = []
        for td in tr.find_all('th'):
            txt = utils.get_tag_contents(td)
            if txt and re.search('Gazette\s+Number', txt):
                order.append('download')
            elif txt and re.match('\s*Type\s*$', txt):
                order.append('gztype')
            else:    
                order.append('')
        return order

    def download_metainfos(self, relpath, metainfos, search_url, \
                           postdata, cookiejar):
        dls = []
        for metainfo in metainfos:
            if not 'download' in metainfo:
                continue 

            link   = metainfo['download']
            href   = link.get('href')
            gznum  = utils.get_tag_contents(link)

            if not href or not gznum:
                continue

            reobj = re.search('javascript:__doPostBack\(\'(?P<event_target>[^\']+)\'', href)
            event_target = reobj.groupdict()['event_target']

            newpost = []
            for t in postdata:
                if t[0] == 'ctl00$ContentPlaceHolder1$BtnSearch':
                    continue
                if t[0] == '__EVENTTARGET':
                    t = (t[0], event_target)
                newpost.append(t)   
            gznum = gznum.strip()
            relurl = os.path.join(relpath, gznum)
            if not self.storage_manager.should_download_raw(relurl, None, validurl=False):
                self.logger.info('Doc already exists: %s', relurl)
                continue

            response = self.download_url(search_url, savecookies = cookiejar, \
                                   loadcookies = cookiejar, postdata = newpost) 
            doc = response.webpage
            if not doc:
                self.logger.warn('Not able to download: %s', relurl)
                continue

            updated = False
            if self.storage_manager.save_rawdoc(self.name, relurl, response.srvresponse, doc):
                updated = True
                self.logger.info(u'Saved rawfile %s' % relurl)
            else:
                self.logger.info(u'not able to save the doc %s' % relurl)
            metainfo.pop('download')                
            if self.storage_manager.save_metainfo(self.name, relurl, metainfo):
                updated = True
                self.logger.info(u'Saved metainfo %s' % relurl)

            if updated:        
                dls.append(relurl)

        return dls            


