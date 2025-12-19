import re
import os
import datetime

from collections import namedtuple

from ..utils import utils
from .basegazette import BaseGazette

ParseResults = namedtuple('ParseResults', "issuedate volume_num gznum")

def parse_title(txt):
    #VOL. LX No.9 FRIDAY, 10th MAY, 2024 / 20th VIASAKHA, 1946 (SAKA)
    reobj = re.search(r'vo(l|i)(\.|,)\s*(?P<vol>\w+)(\.)?\s*no\.\s*' + \
                      r'(?P<num>\d+(\(\w+\))?)\s*(,|\.)?\s*[\D,]+\s*' + \
                      r'(?P<day>\d+)\s*(st|nd|rd|th)?\s*(?P<month>\w+)(,|\.)?\s*(?P<year>\d+)', \
                      txt, flags=re.IGNORECASE)
    if reobj is None:
        return None

    g = reobj.groupdict()

    try:
        issuedate = datetime.datetime.strptime(f'{g["day"]}-{g["month"][:3]}-{g["year"]}', '%d-%b-%Y').date()
    except Exception:
        return None
    
    return ParseResults(issuedate, g['vol'], g['num'])

def fix_special_cases(metainfo):
    title = metainfo.get('title', None)

    if title is None:
        return
    
    upload_date = metainfo.get_date().strftime('%Y-%m-%d')
    if title == 'Lakshadweep Building-Bylaw : Extra Odrinary Gazatte Notification-February 2016' and upload_date == '2018-02-15':
        metainfo.set_date(datetime.datetime(2016, 3, 4).date())
        metainfo['volume_num'] = 'LI'
        metainfo['gznum'] = '40'
        del metainfo['title']

    elif title == 'LVIII No.73' and upload_date == '2023-07-04':
        metainfo.set_date(datetime.datetime(2023, 2, 10).date())
        metainfo['volume_num'] = 'LVIII'
        metainfo['gznum'] = '73'
        del metainfo['title']

    elif title == 'Vol LVIII No.72' and upload_date == '2023-07-04':
        metainfo.set_date(datetime.datetime(2023, 2, 7).date())
        metainfo['volume_num'] = 'LVIII'
        metainfo['gznum'] = '72'
        del metainfo['title']

    elif title == 'Affidavits regarding Change of Name & Corrections recieved from Individuals, Gazette Vol.LXI No. 35' and upload_date == '2025-11-04':
        metainfo.set_date(datetime.datetime(2025, 11, 1).date())
        metainfo['volume_num'] = 'LXI'
        metainfo['gznum'] = '35'
        del metainfo['title']

    elif title == 'Notification regarding Constitution of State Level Committee for Wood Based Industries (Dept. of Environment & Forest), Gazette Vol. LXI No.34' and upload_date == '2025-11-04':
        metainfo.set_date(datetime.datetime(2025, 10, 31).date())
        metainfo['volume_num'] = 'LXI'
        metainfo['gznum'] = '34'
        del metainfo['title']

    elif title == 'Re-Publication of notification for conduct of pre-test of first phase of population Census-2027 and Notifcation regarding designation of Kavaratti Police Station as the Nodal Cyber Police Station and Superintendent of Police, Lakshadweep as the Nodal' and upload_date == '2025-11-04':
        metainfo.set_date(datetime.datetime(2025, 10, 27).date())
        metainfo['volume_num'] = 'LXI'
        metainfo['gznum'] = '33'
        del metainfo['title']

class Lakshadweep(BaseGazette):
    def __init__(self, name, storage):
        BaseGazette.__init__(self, name, storage)
        self.baseurl = 'https://lakshadweep.gov.in/document-category/gazatte-notifications/'
        self.hostname = 'lakshadweep.gov.in'
        self.titles_to_ignore = set([ 'Integrated Island Management Plan', 
                                      'CSR Policy of the Lakshadweep Development Corporation Ltd -2017' ])

    def find_nextpage(self, d, curr_page):
        div = d.find('div', {'class': 'pegination'})
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
                    parsed = parse_title(txt)
                    if parsed is None:
                        metainfo['title'] = txt
                    else:
                        metainfo['volume_num'] = parsed.volume_num
                        metainfo['gznum'] = parsed.gznum
                    
                elif col == 'date':
                    date = datetime.datetime.strptime(txt, '%d/%m/%Y').date()
                    metainfo.set_date(date)
                elif col == 'download':
                    metainfo['download'] = td
            i += 1

        fix_special_cases(metainfo)

        metainfos.append(metainfo)

    def parse_results_page(self, webpage, curr_page):
        metainfos = []
        nextpage = None

        d = utils.parse_webpage(webpage, self.parser)
        if d is None:
            self.logger.warning('Unable to parse webpage for page %s', curr_page)
            return metainfos, nextpage

        div = d.find('div', {'class': 'distTableContent'})
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
                    
                    docid = os.path.splitext(os.path.basename(gzurl))[0]
                   
                    relpath = os.path.join(self.name, metadate.__str__())
                    relurl  = os.path.join(relpath, docid)
                    if self.save_gazette(relurl, gzurl, metainfo):
                        dls.append(relurl)

            if nextpage is None:
                break

            pagenum += 1
            response = self.download_url(nextpage['href'])

        self.logger.info(f'Got {len(dls)} Gazettes from {fromdate.date()} to {todate.date()}')
        return dls

if __name__ == '__main__':
    cases = {
        'VOL. LII. No. 18, MONDAY, 12th SEPTEMBER, 2016 /21st BHADRA, 1938 (SAKA)': ParseResults(datetime.datetime(2016, 9, 12).date(), 'LII', '18'),
        'VOL. LVI. NO. 26 WEDNESDAY,23rd SEPTEMBER,2020/1st ASVINA, 1941(SAKA)': ParseResults(datetime.datetime(2020, 9, 23).date(), 'LVI', '26'),
        'LVIII No.73': None,
        'Vol LVIII No.72': None,
        'Gazette.VOL.LVII.No.37. 20th December,2021': ParseResults(datetime.datetime(2021, 12, 20).date(), 'LVII', '37'),
    }

    for txt, expected in cases.items():
        print(f'checking "{txt}"')
        result = parse_title(txt)
        print(f'{result=}')
        assert result == expected
