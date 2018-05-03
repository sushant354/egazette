import urllib
import re
import os
import datetime

from basegazette import BaseGazette
import utils

class Punjab(BaseGazette):
    def __init__(self, name, storage):
        BaseGazette.__init__(self, name, storage)
        self.hostname  = 'esarkar.punjab.gov.in'
        self.searchurl = 'http://esarkar.punjab.gov.in/web/guest/customepage?p_p_id=guestPortlet&p_p_lifecycle=1&p_p_state=normal&p_p_mode=view&p_p_col_id=column-1&p_p_col_count=1&requestType=ApplicationRH&actionVal=searchRecord&queryType=Select&screenId=400176'
        self.start_date   = datetime.date(2007, 1, 1)
       
    def get_post_data(self, dateobj):
        datestr = utils.dateobj_to_str(dateobj, '/')
        postdata = [\
            ('cmb_Cat', '-1'), ('cmb_Name', '-1'), ('cmb_Not_For', '-1'),     \
            ('ComboDept', '-1'), ('eAttachId', ''), ('freetextradio', 'No'),  \
            ('NewSearchFlag', 'false'), ('PriorityName', '--Select--'),       \
            ('refDocId', ''), ('reportEndIndex', '10'),                       \
            ('reportStartIndex', '1'), ('txtEmail', ''), ('txtFreeText', ''), \
            ('txtFrom', datestr), ('txtGazetteNo', ''), ('txtNotNo', ''),     \
            ('txtNotTitle', ''), ('txtTo', datestr), \
        ]
        return postdata
      
    def download_oneday(self, relpath, dateobj):
        dls = []
        postdata = self.get_post_data(dateobj)
        response = self.download_url(self.searchurl, postdata = postdata)

        if not response or not response.webpage:
            self.logger.warn('Could not download search result for date %s', \
                              dateobj)
            return dls
        
        d = utils.parse_webpage(response.webpage, self.parser)
        if not d:
            self.logger.warn('Could not parse search result for date %s', \
                              dateobj)
            return dls
        
        minfos = self.get_metainfos(d, dateobj)
        for metainfo in minfos:
            if 'docid' not in metainfo:
                self.logger.warn('Ignoring metainfo: %s', metainfo)
                continue

            filename = metainfo.pop('docid')
            relurl   = os.path.join(relpath, filename)
            gzurl    = self.get_doc_url(filename)
            if self.save_gazette(relurl, gzurl, metainfo):
                dls.append(relurl)

        return dls        

    def get_metainfos(self, d, dateobj):             
        minfos = []
        tables = d.find_all('table', {'id': 'tblData'})
        if len(tables) == 0:
            self.logger.warn('Could not find the result table for %s', dateobj)
            return minfos

        
        order  = None
        for tr in tables[0].find_all('tr'):   
            if not order:
                order = self.get_field_order(tr)
                continue

            metainfo = self.process_row(tr, order, dateobj)    
            if metainfo:
                minfos.append(metainfo)

        # group metainfo by docid
        docids = {}
        final  = []
        for metainfo in minfos:        
            if 'docid' in metainfo:
                docid = metainfo['docid'] 
                if docid in docids:
                    last = docids[docid]
                    if 'additional' not in last:
                        last['additional']= []
                    metainfo.pop('docid')    
                    last['additional'].append(metainfo)
                else:
                    final.append(metainfo)
                    docids[docid] = metainfo    
        return final

    def get_field_order(self, tr):
        order = []
        for td in tr.find_all('td'):
            txt = utils.get_tag_contents(td)
            if txt and re.search('Department', txt):
                order.append('department')
            elif txt and re.search('Notification\s+No', txt):
                order.append('notification_num')
            elif txt and re.search('Subject', txt):
                order.append('subject')
            elif txt and re.search('Notification\s+For', txt):
                order.append('notification_type')
            elif txt and re.search('Gazette\s+No', txt):
                order.append('gznum')
            elif txt and re.search('Type', txt):
                order.append('gztype')
            elif txt and re.search('Category', txt):
                order.append('category')
            elif txt and re.search('Detail', txt):
                order.append('download')
            else:    
                order.append('')

        return order
    
    def get_doc_url(self, docid):
        href = '/web/guest/customepage?p_p_id=guestPortlet&p_p_lifecycle=1&p_p_state=exclusive&p_p_mode=view&p_p_col_id=column-1&p_p_col_count=1&requestType=ApplicationRH&actionVal=openAttachmentFile&queryType=Select&screenId=400176&refDocId=%s' % docid 
        return urllib.basejoin(self.searchurl, href)

    def process_row(self, tr, order, dateobj):
        metainfo = utils.MetaInfo()
        metainfo.set_date(dateobj)
        i = 0
        for td in tr.find_all('td'):
            if len(order) > i:
                if order[i] in ['department', 'notification_num', 'subject', \
                            'notification_type', 'gznum', 'gztype', 'category']:
                    txt = utils.get_tag_contents(td)
                    metainfo[order[i]] = txt
                elif order[i] == 'download':
                    link = td.find('a')
                    if link and link.get('onclick'):
                        onclick = link.get('onclick')
                        reobj   = re.search('\d+', onclick) 
                        if reobj:
                            metainfo['docid'] = onclick[reobj.start():reobj.end()]
            i += 1           
        return metainfo    
