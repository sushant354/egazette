import re
import os
import datetime

from urllib.parse import urljoin


from ..utils import utils
from .basegazette import BaseGazette


def parse_ng_subject(txt):
    reobj = re.match(r'(Complete)?\s*Normal\s+Gazette\s*-?\s*(of)?\s*(?P<year>\d{4})', txt, flags=re.IGNORECASE)
    if reobj:
        g = reobj.groupdict()
        return { 'part': 'complete', 'year': g['year'] }

    reobj = re.match(r'Normal\s+Gazette\s*-?\s*No\s*\.\s*(?P<from>\d+)\s*to\s*(?P<to>\d+)\s*of\s*(?P<year>\d{4})', txt, flags=re.IGNORECASE)
    if reobj:
        g = reobj.groupdict()
        return { 'part': f'{g["from"]}-{g["to"]}', 'year': g['year'] }

    txt = re.sub(r'(Normal\s+Gazette|Noram\s+Gazette|Norma\s+Gazette)', 'NG', txt)

    reobj = re.match(r'(?P<numb>\d+)?\s*\.?\s*NG\s*(\.)?-?\s*' + 
                      r'(No)?\s*(\.|-)?\s*(?P<numa>\d+)?\s*(,|\.)?\s*' + 
                      r'(part\s*(-)?\s*(?P<part>[0-9ivxlcdm]+))?\s*' +
                      r'(,)?\s*(of)?\s*(?P<year>\d{4})?', txt, flags=re.IGNORECASE)
    if reobj:
        g = reobj.groupdict()

        num = g['numb'] if g['numb'] is not None else g['numa']

        ng_info = { 'num': num }

        if g['year'] is not None:
             ng_info['year'] = g['year']

        if g['part'] is not None:
            ng_info['part'] = g['part']

        return ng_info

    return None

class Arunachal(BaseGazette):
    def __init__(self, name, storage):
        BaseGazette.__init__(self, name, storage)
        self.baseurl  = 'https://printing.arunachal.gov.in/display-content.php'
        self.hostname = 'printing.arunachal.gov.in'

    def enhance_metainfo_ng(self, metainfo):
        title = metainfo.get('title')

        parsed = parse_ng_subject(title)
        if parsed is None:
            return

        if 'year' in parsed:
            metainfo['year'] = parsed['year']
        else:
            metainfo['year'] = metainfo.get_date().year

        if 'num' in parsed:
            metainfo['gznum'] = parsed['num']

        if 'part' in parsed:
            metainfo['partnum'] = parsed['part']

    def enhance_metainfo(self, metainfo):
        gztype = metainfo.get_gztype()
        if gztype == 'Ordinary':
            self.enhance_metainfo_ng(metainfo)


    def download_metainfos(self, metainfos, fromdate, todate):
        relurls = []
        for metainfo in metainfos:
            issuedate = metainfo.get_date() 
            if issuedate < fromdate.date() or issuedate > todate.date():
                continue

            download_url = metainfo.pop('download_url')
            download_url = urljoin(self.baseurl, download_url)

            filename = download_url.split('/')[-1].rsplit('.', 1)[0].lower()

            relpath = os.path.join(self.name, issuedate.__str__())
            relurl = os.path.join(relpath, filename)
            if self.save_gazette(relurl, download_url, metainfo):
                relurls.append(relurl)

        return relurls


    def get_column_order(self, tr):
        order = []
        for td in tr.find_all('th'):
            txt = utils.get_tag_contents(td)
            if txt and re.search('Title', txt):
                order.append('title')
            elif txt and re.search('Subject', txt):
                order.append('subject')
            elif txt and re.search('Date\s+of\s+Publication', txt):
                order.append('pubdate')
            elif txt and re.search('Action', txt):
                order.append('action')
            else:
                order.append('')
        return order

    def process_result_row(self, tr, metainfos, order):
        metainfo = utils.MetaInfo()

        i = 0
        for td in tr.find_all('td'):
            if len(order) > i:
                col = order[i]
                txt = utils.get_tag_contents(td)
                if txt:
                    txt = txt.strip()

                if col == 'title':
                    metainfo['title'] = txt
                elif col == 'subject':
                    metainfo.set_subject(txt)
                elif col == 'action':
                    a = td.find('a')
                    href = a.get('href') if a else None
                    if href:
                        metainfo['download_url'] = href
                elif col == 'pubdate':
                    pubdate = datetime.datetime.strptime(txt, '%Y-%m-%d').date()
                    if pubdate is not None:
                        metainfo.set_date(pubdate)
            i += 1

        if 'download_url' in metainfo and 'date' in metainfo:
            metainfos.append(metainfo)


    def parse_results(self, webpage, pagenum):
        metainfos = []
        has_nextpage = False

        d = utils.parse_webpage(webpage, self.parser)
        if d is None:
            self.logger.warning('Unable to parse the %s page', pagenum)
            return metainfos, has_nextpage

        tables = d.find_all('table')
        if len(tables) != 1:
            self.logger.warning('Unable to find results table on page %s', pagenum)
            return metainfos, has_nextpage

        table = tables[0]
        order = None
        for row in table.find_all('tr'):
            if not order:
                order = self.get_column_order(row)
                continue

            self.process_result_row(row, metainfos, order)

        page_links = d.find_all('a', {'class': 'page-link'})
        for link in page_links:
            txt = utils.get_tag_contents(link)
            try:
                if int(txt.strip()) == pagenum + 1:
                    has_nextpage = True
            except Exception:
                continue

        return metainfos, has_nextpage


    def sync_section(self, dls, fromdate, todate, event, menu, submenu, gztype):
        pagenum   = 1

        while True:
            url = self.baseurl + (f'?menu={menu}&' + f'submenu={submenu}&' if submenu is not None else '') + f'page={pagenum}' 

            response = self.download_url(url)
            if response is None or response.webpage is None:
                self.logger.warning('Unable to get data from %s for date %s to date %s', \
                                    self.baseurl, fromdate.date(), todate.date())
                break

            if event.is_set():
                self.logger.warning('Exiting prematurely as timer event is set')
                break

            metainfos, has_nextpage = self.parse_results(response.webpage, pagenum)
            for metainfo in metainfos:
                metainfo.set_gztype(gztype)
                self.enhance_metainfo(metainfo)

            relurls = self.download_metainfos(metainfos, fromdate, todate)

            self.logger.info('Got %d gazettes for pagenum %s', len(relurls), pagenum)
            dls.extend(relurls)

            if not has_nextpage:
                break
            pagenum += 1

    def sync(self, fromdate, todate, event):
        dls = []
        self.logger.info('From date %s to date %s', fromdate.date(), todate.date())

        self.sync_section(dls, fromdate, todate, event, 'Documents', 'Acts / Rules', 'Extraordinary')
        self.sync_section(dls, fromdate, todate, event, 'Documents', 'Normal Gazette', 'Ordinary')
        self.sync_section(dls, fromdate, todate, event, 'Documents', 'Extra Ordinary Gazette', 'Extraordinary')
        #self.sync_section(dls, fromdate, todate, event, 'Documents', 'Archive', 'Ordinary')

        return dls


if __name__ == '__main__':
    ng_cases = {
        'Normal Gazette 2020'              : { 'year': '2020', 'part': 'complete', 'num': None },
        'Complete Normal Gazette of 2023'  : { 'year': '2023', 'part': 'complete', 'num': None },
        'Normal Gazette-2023'              : { 'year': '2023', 'part': 'complete', 'num': None },
        'Normal Gazette No.1 to 24 of 2024': { 'year': '2024', 'part': '1-24',     'num': None },
        'Normal Gazette No 19 of 2024'     : { 'year': '2024', 'part': None,       'num': '19' },
        'Normal Gazette No 21of 2024'      : { 'year': '2024', 'part': None,       'num': '21' },
        'Normal Gazette No. 22 of 2024'    : { 'year': '2024', 'part': None,       'num': '22' },
        'Normal Gazette No.5 of 2024'      : { 'year': '2024', 'part': None,       'num': '5' },
        'NG 4 of 2024'                     : { 'year': '2024', 'part': None,       'num': '4' },
        'NG No.5, Part-I, 2023'            : { 'year': '2023', 'part': 'I',        'num': '5' },
        '1. NG. part-1, 2024'              : { 'year': '2024', 'part': '1',        'num': '1' },
        'NG. No. 6. Part-I,  2023'         : { 'year': '2023', 'part': 'I',        'num': '6' },
        'Normal Gazette No 4 part-4'       : { 'year': None,   'part': '4',        'num': '4' },
        'NG No.2, 2024'                    : { 'year': '2024', 'part': None,       'num': '2' },
    }

    for txt, expected in ng_cases.items():
        result = parse_ng_subject(txt)
        assert result == expected, f'ng: {txt=} {expected=} {result=}'
        print(f'passed: {txt=}')
