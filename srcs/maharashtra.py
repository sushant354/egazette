import re
import os
import datetime

from .andhra import AndhraArchive
from ..utils import utils

class Maharashtra(AndhraArchive):
    def __init__(self, name, storage):
        AndhraArchive.__init__(self, name, storage)
        self.baseurl      = 'https://egazzete.mahaonline.gov.in/Forms/GazetteSearch.aspx'
        self.hostname     = 'egazzete.mahaonline.gov.in'
        self.search_endp  = 'GazetteSearch.aspx'
        self.result_table = 'CPH_GridView2'
        self.start_date   = datetime.datetime(2010, 1, 1)

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
                if t == 'image' or name == 'ctl00$CPH$btnReset':
                    continue

                if name == 'ctl00$CPH$txtToDate' or \
                        name == 'ctl00$CPH$txtfromDate':
                    value = datestr
                elif name == 'ctl00$CPH$btnSearch':
                    value = 'Search'
            elif tag.name == 'select':
                name = tag.get('name')
                if name == 'ctl00$CPH$ddldivision':
                    value = '-----Select----'    
                elif name == 'ctl00$CPH$ddlSection':
                    value =  '-----Select-----'
            if name:
                if value == None:
                    value = ''
                postdata.append((name, value))
        return postdata

    def get_column_order(self, tr):
        order = []
        for th in tr.find_all('th'):
            txt = utils.get_tag_contents(th)
            if txt and re.search('Division\s+Name', txt):
                order.append('division')
            elif txt and re.search('Subject', txt):
                order.append('subject')
            elif txt and re.search('View\s+Gazette', txt):
                order.append('download')
            elif txt and re.search('Section\s+Name', txt):
                order.append('partnum')
            elif txt and re.search('Gazette\s+Type', txt):
                order.append('gztype')
            else:
                order.append('')
        return order

    def process_result_row(self, tr, metainfos, dateobj, order):
        metainfo = utils.MetaInfo()
        metainfo.set_date(dateobj)

        i = 0
        for td in tr.find_all('td'):
            if len(order) > i:
                col = order[i]
                txt = utils.get_tag_contents(td)
                if txt:
                    txt = txt.strip()
                else:
                    continue

                if col == 'gztype':
                    metainfo.set_gztype(txt)
                elif col == 'download':
                    link = td.find('a')
                    if link:
                        href = link.get('href')
                        if href:
                            metainfo['download'] = href
                elif col in ['partnum', 'division', 'subject']:
                    metainfo[col] = txt
  
            i += 1
        if 'download' not in metainfo:
            self.logger.warn('No download link, ignoring: %s', tr)
        else:
            metainfos.append(metainfo)
            
    def download_metainfos(self, relpath, metainfos, search_url, \
                           postdata, cookiejar):
        dls = []
        for metainfo in metainfos:
            if 'download' not in metainfo or 'gztype' not in metainfo:
                self.logger.warn('Required fields not present. Ignoring- %s' % metainfo) 
                continue

            href = metainfo.pop('download')
            reobj = re.search('javascript:__doPostBack\(\'(?P<event_target>[^\']+)\'', href)
            if not reobj:
                self.logger.warn('No event_target in the gazette link. Ignoring - %s' % metainfo)
                continue 

            groupdict    = reobj.groupdict()
            event_target = groupdict['event_target']

            newpost = []
            for t in postdata:
                if t[0] == 'ctl00$CPH$btnSearch':
                    continue
                if t[0] == '__EVENTTARGET':
                    t = (t[0], event_target)

                newpost.append(t)
                   
            gztype = metainfo['gztype']
            if 'division' in metainfo:
                gztype = '%s_%s' % (gztype, metainfo['division'])
            if 'partnum' in metainfo:
                gztype = '%s_%s' % (gztype, metainfo['partnum'])

            gztype, n = re.subn('[()\s-]+', '-', gztype)
            relurl = os.path.join(relpath, gztype)
            if self.save_gazette(relurl, search_url, metainfo, \
                                 postdata = newpost, cookiefile = cookiejar, \
                                 validurl = False):
                dls.append(relurl)

        return dls
