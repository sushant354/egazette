import re
import os
import urllib.request
import urllib.parse
import urllib.error
import datetime

import wayback

from ..utils import utils
from .basegazette import BaseGazette

class Puducherry(BaseGazette):
    def __init__(self, name, storage):
        BaseGazette.__init__(self, name, storage)
        self.baseurl  = 'https://styandptg.py.gov.in/{}/{}{}{:02}.{}'
        self.hostname = 'styandptg.py.gov.in'
        self.page_cache = {}
        self.year = None
        self.wayback_client = None

    def get_wayback_client(self):
        if self.wayback_client is None:
            wayback_session = wayback.WaybackSession(retries=10)
            self.wayback_client = wayback.WaybackClient(session=wayback_session)

        return self.wayback_client

    def download_url(self, url, loadcookies = None, savecookies = None, \
                     postdata = None, referer = None, \
                     encodepost= True, headers = {}):

        url = url.replace('.puducherry.gov.in', '.py.gov.in')
        response = BaseGazette.download_url(self, url, loadcookies=loadcookies, \
                                            savecookies=savecookies, postdata=postdata, \
                                            encodepost=encodepost, headers=headers)
        if response is not None:
            return response

        if self.year >= 2021:
            return response

        wb_client = self.get_wayback_client()
        found = None
        for record in wb_client.search(url):
            if record.status_code == 200:
                found = record
                break

        if found is None:
            return None

        response = BaseGazette.download_url(self, found.raw_url)

        if response is None or response.webpage is None:
            return None

        return response

    def download_url_cached(self, url):

        if url not in self.page_cache:
            response = self.download_url(url)

            self.page_cache[url] = response

        return self.page_cache[url]
 
    def get_field_order(self, tr):
        order  = []

        for td in tr.find_all(['th', 'td']):
            txt = self.get_tag_contents(td)

            if txt and re.search(r'Date\s+of\s+Issue', txt):
                order.append('issuedate')
            elif txt and re.search(r'(Contents|Subject|supplement\s+with\s+Gazette)', txt):
                order.append('contents')
            elif txt and re.search(r'Issue\s+', txt):
                order.append('gznum')
            else:
                order.append('')    
        
        for field in ['issuedate', 'gznum', 'contents']:
            if field not in order:
                return None

        return order
 
    def process_row(self, metainfos, tr, order, dateobj):
        metainfo = utils.MetaInfo()

        i = 0
        issuedate = None
        for td in tr.find_all(['th', 'td']):
            if len(order) > i:
                txt = self.get_tag_contents(td)
                if order[i] == 'gznum':
                    metainfo['gznum'] = txt
                elif order[i] == 'issuedate':
                    metainfo['issuedate'] = td
                    reobj = re.search(r'(?P<day>\d+)(\.|/)(?P<month>\d+)(\.|/)(?P<year>\d+)', txt)
                    if reobj:
                        groupdict = reobj.groupdict()
                        try:
                            year = int(groupdict['year'])
                            if year < 2000:
                                year += 2000
                            issuedate = datetime.datetime(year, int(groupdict['month']), int(groupdict['day'])).date()
                        except Exception:
                            pass
                    if issuedate is None:
                        self.logger.warning('Unable to parse date string %s', txt)
                elif order[i] == 'contents':
                    metainfo['contents'] = td
            i += 1

        for k in ['gznum', 'issuedate', 'contents']:
            if k not in metainfo:
                return

        if issuedate is None or issuedate != dateobj:
            return

        metainfo.set_date(dateobj)
        metainfos.append(metainfo)

    def process_results(self, metainfos, webpage, dateobj):
        d = utils.parse_webpage(webpage, self.parser) 
        if d is None:
            self.logger.info('Unable to parse result page for date: %s', dateobj)
            return

        order = None
        for table in d.find_all('table'):
            if order is not None:
                break

            if table.find('table') is not None:
                continue

            for tr in table.find_all('tr'):
                if not order:
                    order = self.get_field_order(tr)
                    continue

                if tr.find('a') is None:
                    continue

                self.process_row(metainfos, tr, order, dateobj)

    def download_metainfo(self, dls, relpath, metainfo):
        gzurl = metainfo.pop('gzurl')
        docid = metainfo.pop('docid')

        relurl = os.path.join(relpath, docid)

        if self.save_gazette(relurl, gzurl, metainfo):
            dls.append(relurl)

    def get_tag_contents(self, tag):
        txt = utils.get_tag_contents(tag).strip()

        txt = txt.replace('\r', ' ')
        txt = txt.replace('\n', ' ')

        txt = ' '.join(txt.split())

        txt = txt.strip()

        return txt

    def drop_colons(self, txt):
        if txt.startswith(':'):
            txt = txt[1:]

        if txt.endswith(':'):
            txt = txt[:-1]

        txt = txt.strip()

        return txt

    def download_oneday(self, relpath, dateobj):
        dls = []

        year  = dateobj.year
        month = dateobj.strftime('%b').lower()

        self.year = year

        section_infos = {
            'Ordinary'         : { 'prefix': 'ordinary',     'gztype': 'Ordinary',      'partnum': None },
            'Supplementary'    : { 'prefix': 'supple',       'gztype': 'Supplementary', 'partnum': None },
            'Extraordinary I'  : { 'prefix': 'exordinary1',  'gztype': 'Extraordinary', 'partnum': 'I'  },
            'Extraordinary II' : { 'prefix': 'exordinaryII', 'gztype': 'Extraordinary', 'partnum': 'II' },
        }
        
        for section, info in section_infos.items():
            metainfos = []

            prefix  = info['prefix']
            gztype  = info['gztype']
            partnum = info['partnum']

            docid_prefix = "-".join(section.lower().split(" "))

            ext = 'html' if year >= 2018 else 'htm'
            url = self.baseurl.format(year, prefix, month, year % 100, ext)

            response = self.download_url_cached(url)
            if not response or not response.webpage:
                self.logger.warning('Unable to get year page %s for date %s', url, dateobj)
                continue

            self.process_results(metainfos, response.webpage, dateobj)

            for metainfo in metainfos:
                metainfo.set_gztype(gztype)
                if partnum:
                    metainfo['partnum'] = partnum

                gznum          = metainfo['gznum']
                contents       = metainfo.pop('contents')
                issuedate_node = metainfo.pop('issuedate')

                if section == 'Ordinary':
                    for link in contents.find_all('a'):
                        txt = self.get_tag_contents(link).strip()
                        if txt == '' or txt == 's':
                            continue

                        category = txt
                        reobj = re.search(r'OG\s+No\.\d+\s+dt\.\d+\.\d+\.\d+', txt)
                        if reobj:
                            category = 'Combined'

                        new_metainfo = utils.MetaInfo()
                        new_metainfo.set_date(metainfo.get_date())
                        new_metainfo.set_gztype('Ordinary')
                        new_metainfo['gznum']    = gznum
                        new_metainfo['category'] = category
                        new_metainfo['gzurl']    = urllib.parse.urljoin(url, link.get('href'))

                        category = "-".join(category.lower().split(' '))

                        new_metainfo['docid'] = f'{docid_prefix}-issue-{gznum}-{category}'

                        self.download_metainfo(dls, relpath, new_metainfo)

                elif section == 'Supplementary':
                    link = contents.find('a')

                    metainfo['gzurl'] = urllib.parse.urljoin(url, link.get('href'))

                    full_txt = self.get_tag_contents(contents)

                    strong = contents.find('strong')
                    txt = ''
                    if strong:
                        txt = self.get_tag_contents(strong)
                        metainfo['department'] = txt

                    if full_txt.startswith(txt):
                        metainfo['subject'] = full_txt[len(txt):].strip()

                    metainfo['docid'] = f'{docid_prefix}-issue-{gznum}'

                    self.download_metainfo(dls, relpath, metainfo)

                else:
                    link = issuedate_node.find('a')
                    metainfo['gzurl'] = urllib.parse.urljoin(url, link.get('href'))

                    full_txt = self.get_tag_contents(contents)

                    fonts = contents.find_all(['font', 'strong'])
                    txts = [ self.get_tag_contents(f) for f in fonts ]
                    txts = [ t for t in txts if t != '' ]

                    to_remove = ' '.join(txts)
                    if full_txt.startswith(to_remove):
                        metainfo['subject'] = full_txt[len(to_remove):].strip()

                    txts = [ self.drop_colons(txt) for txt in txts ]
                    if len(txts) > 0:
                        metainfo['department'] = txts[0]
                    if len(txts) > 1:
                        metainfo['category'] = txts[1]

                    metainfo['docid'] = f'{docid_prefix}-issue-{gznum}'

                    self.download_metainfo(dls, relpath, metainfo)

        return dls