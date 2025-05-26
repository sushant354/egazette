import re
import os

from ..utils import utils
from .central import CentralBase

class Bihar(CentralBase):
    def __init__(self, name, storage):
        CentralBase.__init__(self, name, storage)
        self.hostname   = 'egazette.bih.nic.in'
        self.baseurl    = 'http://egazette.bih.nic.in/SearchGazette.aspx'
        self.search_endp = 'SearchGazette.aspx'
        self.result_table = 'ctl00_ContentPlaceHolder1_DetailView'

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
                    value = ''
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

    def find_next_page(self, tr, curr_page):
        for tr in tr.find_all('tr'):
            if tr.find('tr') != None:
                continue

            nextpage = None
            for td in tr.find_all('td'):
                txt = utils.get_tag_contents(td)
                if not txt:
                    continue
                txt = txt.strip()
                if not re.match('\d+$', txt):
                    continue
                v = int(txt)
                if v == curr_page +1 and td.find('a') != None:
                    nextpage = td.find('a')
                    return nextpage
        return None

    def download_nextpage(self, nextpage, search_url, postdata, cookiejar):
        href   = nextpage.get('href')
        if href == None:
            return None

        reobj = re.search('javascript:__doPostBack\(\'(?P<event_target>[^\']+)\',\s*\'(?P<event_arg>[^\']+)\'', href)
        if not reobj:
            return None

        groupdict    = reobj.groupdict()
        event_target = groupdict['event_target']
        event_arg    = groupdict['event_arg']

        newpost = []
        for t in postdata:
            if t[0] == 'ctl00$ContentPlaceHolder1$BtnSearch':
                continue
            if t[0] == '__EVENTTARGET':
                t = (t[0], event_target)
            if t[0] == '__EVENTARGUMENT':
                t = (t[0], event_arg)

            newpost.append(t)

        response = self.download_url(search_url, savecookies = cookiejar, \
                                   loadcookies = cookiejar, postdata = newpost)
        return response

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

            reobj = re.search('javascript:__doPostBack\(\'(?P<event_target>[^\']+)\',\s*\'(?P<event_arg>[^\']*)\'', href)
            groupdict    = reobj.groupdict()
            event_target = groupdict['event_target']
            event_arg    = groupdict['event_arg']
            if event_arg:
                continue

            newpost = []
            for t in postdata:
                if t[0] == 'ctl00$ContentPlaceHolder1$BtnSearch':
                    continue
                if t[0] == '__EVENTTARGET':
                    t = (t[0], event_target)

                newpost.append(t)   

            gznum = gznum.strip()
            relurl = os.path.join(relpath, gznum)
            metainfo.pop('download')
            if self.save_gazette(relurl, search_url, metainfo, \
                                 postdata = newpost, cookiefile = cookiejar, \
                                 validurl = False):
                dls.append(relurl)

        return dls            


