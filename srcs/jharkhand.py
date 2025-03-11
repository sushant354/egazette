import re
import os

from .andhra import AndhraArchive
from ..utils import utils
from ..utils.metainfo import MetaInfo

class Jharkhand(AndhraArchive):
    def __init__(self, name, storage):
        AndhraArchive.__init__(self, name, storage)
        self.baseurl      = 'https://egazette.jharkhand.gov.in/SearchGazette.aspx'
        self.hostname     = 'egazette.jharkhand.gov.in'
        self.search_endp  = 'SearchGazette.aspx'

        self.result_table = 'ctl00_ContentPlaceHolder1_DetailView'

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

                if name == 'ctl00$ContentPlaceHolder1$TYPE' and not value == 'RadioButton1':
                    continue

                if name == 'ctl00$ContentPlaceHolder1$BtnCancel':
                    continue

                if name == 'ctl00$ContentPlaceHolder1$TextBox1' or \
                        name == 'ctl00$ContentPlaceHolder1$TextBox2':
                    value = datestr
                elif name == 'ctl00$ContentPlaceHolder1$CheckBoxYearAll':
                    value = 'on'    
            elif tag.name == 'select':
                name = tag.get('name')
                if name == 'ctl00$ContentPlaceHolder1$ddlYear':
                    continue
                elif name == 'ctl00$ContentPlaceHolder1$ddlFilter':
                    value = '1'

            if name:
                if value == None:
                    value = ''
                postdata.append((name, value))
        return postdata

    def get_column_order(self, tr):
        order = []
        for th in tr.find_all('th'):
            txt = utils.get_tag_contents(th)
            if txt and re.match('\s*Type', txt):
                order.append('gztype')
            elif txt and re.search('Gazette\s+Number', txt):
                order.append('gznum')
            else:
                order.append('')
        return order

    def process_result_row(self, tr, metainfos, dateobj, order):
        tds = tr.find_all('td')
        if len(tds) != len(order):
            return

        metainfo = MetaInfo()
        metainfos.append(metainfo)
        metainfo.set_date(dateobj)

        i = 0
        for td in tds:
            if len(order) > i:
                col = order[i]
                txt = utils.get_tag_contents(td)
                if txt:
                    txt = txt.strip()
                else:
                    continue

                if col == 'gztype':
                    metainfo.set_gztype(txt)

                elif col == 'gznum':
                    metainfo['gznum'] = txt
                    link = td.find('a')
                    if link and link.get('href'):
                        metainfo['download'] = link.get('href')

            i += 1

    def download_metainfos(self, relpath, metainfos, search_url, \
                           postdata, cookiejar):
        dls = []
        for metainfo in metainfos:
            if 'download' not in metainfo or 'gznum' not in metainfo:
                self.logger.warning('Required fields not present. Ignoring- %s' % metainfo)
                continue

            href = metainfo.pop('download')
            reobj = re.search('javascript:__doPostBack\(\'(?P<event_target>[^\']+)\'', href)
            if not reobj:
                self.logger.warning('No event_target in the gazette link. Ignoring - %s' % metainfo)
                continue

            groupdict    = reobj.groupdict()
            event_target = groupdict['event_target']

            newpost = []
            for t in postdata:
                if t[0] == 'ctl00$ContentPlaceHolder1$BtnSearch':
                    continue
                if t[0] == '__EVENTTARGET':
                    t = (t[0], event_target)

                newpost.append(t)

            gznum = metainfo['gznum']
            gznum, n = re.subn('[\s]+', '', gznum)
            relurl = os.path.join(relpath, gznum)
            if self.save_gazette(relurl, search_url, metainfo, \
                                 postdata = newpost, cookiefile = cookiejar, \
                                 validurl = False):
                dls.append(relurl)

        return dls

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


