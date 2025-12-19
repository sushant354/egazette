import re
import os
import datetime

from collections import namedtuple

from ..utils import utils
from .basegazette import BaseGazette

ParseResults = namedtuple('ParseResults', "gznum gztype series_num")

def parse_title(txt, overrides={}):
    if txt in overrides:
        return overrides[txt]

    reobj = re.search(r'official\s+gazette\s*(:|-|–|—)?\s*series\s*(-|–|—)*\s*' + \
                      r'(?P<series>.+)\s+no\s*(\.)?\s*(?P<num>\d+)', txt, flags=re.IGNORECASE)
    if reobj:
        g = reobj.groupdict()
        return ParseResults(g['num'], 'Ordinary', g['series'])

    reobj = re.search(r'official\s+gazette\s*[:-]?\s*extra\s*' + \
                      r'ordinary\s+(no)?\s*[\.:]?\s*(?P<num>\d+)', txt, flags=re.IGNORECASE)
    if reobj:
        g = reobj.groupdict()
        return ParseResults(g['num'], 'Extraordinary', None)

    return None

class DadraNagarHaveli(BaseGazette):
    def __init__(self, name, storage):
        BaseGazette.__init__(self, name, storage)
        self.baseurl = 'https://ddd.gov.in/document-category/official-gazette/'
        self.hostname = 'ddd.gov.in'
        self.titles_to_ignore = set([
            'Office of the Secretary (Revenue) : Dadra and Nagar haveli and Daman and Diu Tenancy Rules, 2024',
            'M/s. Pendulum Store, : Shifting & Re-installation of Audio Visual equipment of Conference Hall, Secretariat Nani Daman to new conference hall, vidyut bhavan, Kachigam, Nani Daman.',
            'M/s. Shanti Procon LLP., : Providing Aluminum Partition and other Miscellaneous work at Vidyut Bhavan, Kachigam, Daman.',
            'Office of the Secretary (Revenue) : The draft Dadra and Nagar Haveli and Daman and Diu Tenancy Regulation, 2021',
            'Cooperative Societies Department : Notification regarding classification of Co-operative Societies',
        ])

        self.parse_overrides = {
            'Official Gazette, Cooperative Societies Department : Official copy of Dadra and Nagar Haveli and Daman & Diu Co-operative Societies Regulation, 2024': ParseResults('01', 'Ordinary', 'I'),
            'Official Gazette, Cooperative Societies Department : Official copy of Dadra and Nagar Haveli and Daman & Diu Co-operative Societies Rules, 2025': ParseResults('01', 'Ordinary', 'I'),
            'Planning and Development Authority : Notification Regarding First Amendment to the General Development Rules – 2023 Daman': ParseResults('125', 'Extraordinary', None),
        }


    def find_nextpage(self, d, curr_page):
        div = d.find('div', {'class': 'pagination'})
        if div is None:
            self.logger.warning('Unable to get pagination div for page %s', curr_page)
            return None

        return utils.find_next_page(div, curr_page)
    
    def get_column_order(self, tr):
        order = []
        for th in tr.find_all('th'):
            txt = utils.get_tag_contents(th)
            if txt and re.search(r'Title', txt):
                order.append('title')
            elif txt and re.search(r'Date', txt):
                order.append('date')
            elif txt and re.search(r'View\s*/\s*Download', txt):
                order.append('download')
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
                    parsed = parse_title(txt, overrides=self.parse_overrides)
                    if parsed is None:
                        metainfo['title'] = txt
                    else:
                        metainfo.set_gztype(parsed.gztype)
                        metainfo['gznum'] = parsed.gznum
                        series_num = parsed.series_num
                        if series_num is not None:
                            metainfo['series_num'] = series_num
                    
                elif col == 'date':
                    metainfo.set_date(datetime.datetime.strptime(txt, '%d/%m/%Y').date())

                elif col == 'download':
                    metainfo['download'] = td
            i += 1

        #fix_special_cases(metainfo)

        if 'title' not in metainfo:
            metainfos.append(metainfo)
        else:
            title = metainfo['title']
            if title not in self.titles_to_ignore:
                self.logger.warning('Invalid metainfo %s', metainfo)


    def parse_results_page(self, webpage, curr_page):
        metainfos = []
        nextpage = None

        d = utils.parse_webpage(webpage, self.parser)
        if d is None:
            self.logger.warning('Unable to parse webpage for page %s', curr_page)
            return metainfos, nextpage

        div = d.find('div', {'class': 'data-table-container'})
        if div is None:
            self.logger.warning('Unable to get div for page %s', curr_page)
            return metainfos, nextpage

        table = div.find('table')
        if table is None:
            self.logger.warning('Unable to get table for page %s', curr_page)
            return metainfos, nextpage

        order = None
        for tr in table.find_all('tr'):
            if order is None:
                order = self.get_column_order(tr)
                continue

            self.process_result_row(tr, metainfos, order)

        nextpage = self.find_nextpage(d, curr_page)
        
        return metainfos, nextpage

    def sync(self, fromdate, todate, event):
        dls = []

        response = self.download_url(self.baseurl)
        pagenum = 1
        while response is not None and response.webpage is not None:

            if event.is_set():
                self.logger.warning('Exiting prematurely as timer event is set')
                return dls

            metainfos, nextpage = self.parse_results_page(response.webpage, pagenum)

            for metainfo in metainfos:
                metadate = metainfo.get_date()

                if fromdate.date() <= metadate <= todate.date():
                    download = metainfo.pop('download')

                    link = download.find('a')
                    if link is None or link.get('href') is None:
                        continue
                    gzurl = link.get('href')

                    docid = metainfo.get_gztype().lower()
                    series_num = metainfo.get('series_num', None)
                    if series_num is not None:
                        docid += f'-{series_num.lower()}'
                    docid += f'-{metainfo["gznum"]}'

                    relpath = os.path.join(self.name, metadate.__str__())
                    relurl  = os.path.join(relpath, docid)
                    if self.save_gazette(relurl, gzurl, metainfo):
                        dls.append(relurl)

            if nextpage is None:
                break

            pagenum += 1
            response = self.download_url(nextpage['href'])
        self.logger.info(f'Got {len(dls)} Gazettes for the date from {fromdate.date()} to {todate.date()}')
        return dls

if __name__ == '__main__':
    cases = {
        'Official Gazette Extraordinary : 87': ParseResults('87', 'Extraordinary', None),
        'Official Gazette : Extraordinary No.88': ParseResults('88', 'Extraordinary', None),
        'Official Gazette : SERIES – II No. 18': ParseResults('18', 'Ordinary', 'II'),
        'Official Gazette : SERIES —1 No. 05': ParseResults('05', 'Ordinary', '1'),
        'Official Gazette : Series II No.12': ParseResults('12', 'Ordinary', 'II'),
    }

    for txt, expected in cases.items():
        print(f'checking "{txt}"')
        result = parse_title(txt)
        assert result == expected, f'{result=} {expected=}'