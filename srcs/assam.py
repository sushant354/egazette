import urllib.parse
import re
import os
import datetime

from ..utils import utils
from .basegazette import BaseGazette

class AssamBase(BaseGazette):
    def __init__(self, name, storage):
        BaseGazette.__init__(self, name, storage)
        self.baseurl  = 'https://dpns.assam.gov.in/home.php'
        self.hostname = 'dpns.assam.gov.in'
        self.page_cache = {}

        self.months = [ 'January', 'February', 'March', \
                        'April', 'May', 'June', 'July', 'August', \
                        'September', 'October', 'November', 'December' ]

        self.months = [ m.lower() for m in self.months ]
        month_match_str = '|'.join(self.months)

        self.day_suffixes = [ 'th', 'st', 'rd' ]
        day_suffix_match_str = '|'.join(self.day_suffixes)

        self.date_name_re = r'Daterd|Dateded|Dated|Datwd|Dared|Dates|Datded|Datd|Dateed'
        self.base_date_re = rf"(?P<day>\d+)({day_suffix_match_str})?\s*(-| )+\s*(?P<month>(\d+|({month_match_str})))\s*(-| )+\s*(?P<year>\d+)"
        self.full_date_re = r"Date(\s|_|-)+" + self.base_date_re



    def download_url_cached(self, url):

        if url not in self.page_cache:
            response = self.download_url(url)

            self.page_cache[url] = response

        return self.page_cache[url]
 

    def get_yearly_links(self, gztype):
        olinks = {}
        elinks = {}

        response = self.download_url_cached(self.baseurl)
        if response is None or response.webpage is None:
            self.logger.warning('Unable to get %s for getting top links', self.baseurl)
            return olinks, elinks

        d = utils.parse_webpage(response.webpage, self.parser)
        if d is None:
            self.logger.warning('Unable to parse %s for getting top links', self.baseurl)
            return olinks, elinks

        for li in d.find_all('li', {'data-level': '2'}):
            link = li.find('a')
            if link is None:
                continue

            href = link.get('href')
            if href is None:
                continue

            txt = utils.get_tag_contents(li)
            txt = txt.strip()

            reobj = re.match('^Extraordinary-(?P<year>\d+)$', txt)
            if reobj:
                year = reobj.groupdict()['year']
                elinks[year] = urllib.parse.urljoin(self.baseurl, href)
                continue

            reobj = re.match('^Weekly\s+Gazette-(?P<year>\d+)$', txt)
            if reobj:
                year = reobj.groupdict()['year']
                olinks[year] = urllib.parse.urljoin(self.baseurl, href)
                continue

        if gztype == 'Extraordinary':
            return elinks
        elif gztype == 'Weekly':
            return olinks
        else:
            return  {}

    def process_row(self, li):
        link = li.find('a')
        if link is None:
            return None

        metainfo = utils.MetaInfo()
        metainfo['subject'] = utils.get_tag_contents(link)
        metainfo['download'] = link.get('href')

        return metainfo


    def parse_results(self, webpage, url, curr_page):
        metainfos = []
        nextpage  = None
        d = utils.parse_webpage(webpage, self.parser)
        if d is None:
            self.logger('Unable to parse webpage for %s', url)
            return metainfos, nextpage

        div = d.find('div', {'class': 'content-portion'})
        if div is None:
            self.logger('Unable to locate relevant div in webpage for %s', url)
            return metainfos, nextpage

        uls = div.find_all('ul')
        pager_ul = None
        data_ul  = None
        for ul in uls:
            classes = ul.get('class')
            if classes is None:
                data_ul = ul
            elif 'pager' in classes:
                pager_ul = ul

        if data_ul is None:
            return metainfos, nextpage

        for li in data_ul.find_all('li'):
            metainfo = self.process_row(li)
            if metainfo is not None:
                metainfo['pageurl'] = url
                metainfos.append(metainfo)

        if pager_ul is not None:
            nextpage = utils.find_next_page(pager_ul, curr_page)

        return metainfos, nextpage

    def parse_download_page(self, url, metainfo):
        infos = []
        response = self.download_url(url)
        if response is None or response.webpage is None:
            self.logger.warning('Unable to get page %s for %s', url, metainfo)
            return infos
        d = utils.parse_webpage(response.webpage, self.parser)
        if d is None:
            self.logger.warning('Unable to parse page %s for %s', url, metainfo)
            return infos

        div = d.find('div', {'class': 'content-portion'})
        if div is None:
            self.logger.warning('Unable to locate relevant div in webpage for %s for %s', url, metainfo)
            return infos

        table = div.find('table')
        if table is None:
            self.logger.warning('Unable to locate download table in webpage for %s for %s', url, metainfo)
            return infos

        for tr in table.find_all('tr'):
            if tr.find('a') is None:
                continue

            tds = tr.find_all('td')
            file_td = tds[0]
            filename = utils.get_tag_contents(file_td)
            filename = filename.strip()

            link = file_td.find('a')
            if link and link.get('href'):
                download_url = link.get('href')
                download_url = urllib.parse.urljoin(url, download_url)
                infos.append([filename, download_url])

        return infos

    def group_to_date(self, g):
        daystr = g['day']
        for s in self.day_suffixes:
            daystr.replace(s, '')
        day = int(daystr)
    
        monthstr = g['month']
        try:
            mindex = self.months.index(monthstr.lower())
            month = mindex + 1
        except ValueError:
            month = int(monthstr)
    
        year = int(g['year'])
        if year < 100:
            year += 2000
    
        d = None
        err = None
        try:
            d = datetime.datetime(year, month, day).date()
        except Exception:
            err = f'Unable to create date from {year=}, {month=}, {day=}'
            
        return d, err

    def parse_subject(self, txt):
        txt = re.sub(self.date_name_re, 'Date', txt, flags=re.IGNORECASE)
        txt = re.sub(r'(\(|\)|_|-)', ' ', txt)

        if txt.lower().find('date') <= 0:
            date_re = self.base_date_re
        else:
            date_re = self.full_date_re

        reobj = re.search(date_re, txt, flags=re.IGNORECASE)
        if reobj is not None:
            g = reobj.groupdict()
            d, err = self.group_to_date(g)
            if err is not None:
                self.logger.warning(f'Subject Parsing error: {err}')
            return d
    
        return None


    def parse_main_subject(self, txt):
        txt = re.sub(self.date_name_re, 'Date', txt, flags=re.IGNORECASE)
        txt = re.sub(r'(\(|\)|_|-)', ' ', txt)
    
        if txt.lower().find('date') <= 0:
            date_re = self.base_date_re
        else:
            date_re = self.full_date_re
    
        dates = []
        errs  = []
        for reobj in re.finditer(date_re, txt, flags=re.IGNORECASE):
            g = reobj.groupdict()
            d, err = self.group_to_date(g)
            if d is not None:
                dates.append(d)
            if err is not None:
                errs.append(err)
        if len(dates) == 0:
            self.logger.warning(f'Main Subject Parsing errors: {errs}')
    
        return dates


    def handle_special_cases(self, subject):
        # 2017 page 7
        if subject == 'No. 722 LGL 175-2005-Pt-I-71_PART - B':
            return [ datetime.datetime(2017, 12, 4).date() ]
        if subject == 'No. 722 LGL 175-2005-Pt-I-71_PART - A':
            return [ datetime.datetime(2017, 12, 4).date() ]
        if subject == 'No. 720 LGL 175-2005-Pt-I-71':
            return [ datetime.datetime(2017, 12, 4).date() ]

        # 2017 page 59
        if subject == 'No. 126 ELE.144-2015-712 01-04-17':
            return [ datetime.datetime(2017, 4, 1).date() ]

        # 2018 page 45
        if subject == 'No. 131 WMD.117-2017-25 Dated 16-0218':
            return [ datetime.datetime(2018, 2, 16).date() ]

        # 2019 weekly page 2
        if subject == 'No. 31 Dated 31-06-19':
            return [ datetime.datetime(2019, 7, 31).date() ]

        # 2019 page 22
        if subject == 'No. 306 LGL-247-2015-172 Dated 03-17-19':
            return [ datetime.datetime(2019, 7, 3).date() ]

        # 2019 page 37
        if subject == 'No. 149 PRD 12019-20-2019-PRD(B)-12':
            return [ datetime.datetime(2019, 3, 9).date() ]

        # 2020 page 25
        if subject == 'No. 326  RLA 153-2016-91 Dated 31-06-20':
            return [ datetime.datetime(2020, 7, 31).date() ]

        # 2021 page 8
        if subject == 'No. 538 RLA 92-2021-77 Dated 77-11-21':
            return [ datetime.datetime(2021, 11, 17).date() ]

        # 2021 page 24
        if subject == 'No. 378 FTX 56-2017-659  Dated 10-80-21':
            return [ datetime.datetime(2021, 8, 10).date() ]

        # 2021 page 41
        if subject == 'No. 212 RLA 104-2020-7 30-03-2021':
            return [ datetime.datetime(2021, 3, 30).date() ]

        # 2022 page 0
        if subject == 'No. 791 ECF 262750-2 Dated -12-2022':
            return [ datetime.datetime(2022, 12, 31).date() ]

        # 2022 page 3
        if subject == 'No. 766 AR 41-2022-17 Dated 02-22-2022':
            return [ datetime.datetime(2022, 11, 2).date() ]

        # 2022 page 15
        if subject == 'No. 642 REGN 77-2017-152 Dated 0309-2022':
            return [ datetime.datetime(2022, 9, 3).date() ]

        # 2022 page 23
        if subject == 'No. 642 REGN 77-2017-152 Dated 0309-2022':
            return [ datetime.datetime(2022, 9, 3).date() ]

        # 2022 page 23
        if subject == 'No. 563 UDD (T)245-2022-6 Dated 11-0702022 Part-I, Part-II, Part-III & Part-IV':
            return [ datetime.datetime(2022, 7, 11).date() ]

        # 2022 page 23 inside
        if subject.startswith('no._563_uddt245-2022-6_dated_11-0702022_part-'):
            return [ datetime.datetime(2022, 7, 11).date() ]

        # 2022 page 44
        if subject == 'No. 352 KRA 49-IGGL-Borpalaha-21-20 Dated 044-04-2022':
            return [ datetime.datetime(2022, 4, 4).date() ]
        if subject == 'No. 354 UDD(T) 186-2022-6 02-05-2022 Amguri_compressed':
            return [ datetime.datetime(2022, 5, 2).date() ]

        # 2022 page 56
        if subject == 'No. 234 MRQ 1-2021-18 Dated 0--3-2022':
            return [ datetime.datetime(2022, 3, 9).date() ]

        # 2022 page 68
        if subject == 'No. 115 RLA 8-2022-4 Dated 10-20-22':
            return [ datetime.datetime(2022, 2, 10).date() ]

        # 2023 page 49
        if subject == 'No. 110 LGL 259-2022-52 Dated 18-25-23':
            return [ datetime.datetime(2023, 2, 18).date() ]

        # 2024 page 32
        if subject == 'No. 445 E-544089-52 01-10-24':
            return [ datetime.datetime(2024, 10, 1).date() ]
        if subject == 'No. 444 Ecf No. 374321-53 01-10-24':
            return [ datetime.datetime(2024, 10, 1).date() ]

        # 2024 page 36
        if subject == 'No. 399 eCF 360522-244 Dated 31-09-24':
            return [ datetime.datetime(2024, 8, 31).date() ]

        # 2024 page 44
        if subject == 'No. 320 No. 502108-83 Dated 24-07024 Financial Power':
            return [ datetime.datetime(2024, 7, 24).date() ]

        # 2024 page 49
        if subject == 'No. 269 E-262400-31 Dated -0-07-24':
            return [ datetime.datetime(2024, 7, 4).date() ]

        # 2024 page 53
        if subject == 'No. 231 HMA 19-252-2023-Pol(A)-eCF-375659-64 Dated 10-06-20244':
            return [ datetime.datetime(2024, 6, 10).date() ]

        if subject == 'No. 77 TMV- E 554799-43 5-02-25':
            return [ datetime.datetime(2025, 2, 5).date() ]

        return []

    def dump(self, main_subject, subject, curr_url):

        import json

        parts = curr_url.split('?')
        if len(parts) == 1:
            page = '1'
        else:
            page = parts[1].split('=')[1]

        typ = parts[0].split('/')[-1]

        with open('ordinary_top_urls.jsonl', 'a') as f:
            f.write(json.dumps({'typ': typ, 'page': page, 'main_subject': main_subject, 'subject': subject}))
            f.write('\n')

    def download_metainfo(self, relpath, metainfo, curr_url, dateobj, gztype):
        relurls = []

        main_subject = metainfo.pop('subject')
        href = metainfo.pop('download')

        main_subject = main_subject.strip()

        special_ignore = [
            'No. 216 RMACG', 
            'No. 215 LLE.12-2022-83'
        ]
        if main_subject in special_ignore:
            return relurls

        reobj = re.match(r'^No(.)?\s+\d+(\s*\(?\s*(No|Not)(\.)?\s+(Name|Gazette|Gazatte|Published)\s*\)?)?$', \
                         main_subject, flags=re.IGNORECASE)
        if reobj is not None:
            return relurls

        issuedates = self.handle_special_cases(main_subject)

        if len(issuedates) == 0:
            issuedates = self.parse_main_subject(main_subject)

        if len(issuedates) == 0:
            self.logger.warning('Unable to get dates from %s', main_subject)
            return relurls

        # TODO: a simple 'in' would suffice?
        found_date = False
        for issuedate in issuedates:
            if issuedate == dateobj:
                found_date = True
                break

        if not found_date:
            return relurls

        download_page_url = urllib.parse.urljoin(curr_url, href)
        infos = self.parse_download_page(download_page_url, metainfo)
        for info in infos:
            newmeta = utils.MetaInfo()
            newmeta.set_gztype(gztype)

            subject = info[0]
            gzurl   = info[1]

            issuedate = None
            if len(issuedates) != 0:
                issuedate = issuedates[0]

            if issuedate is None:
                issuedates = self.handle_special_cases(subject)
                if len(issuedates) != 0:
                    issuedate = issuedates[0]

            if issuedate is None:
                issuedate = self.parse_subject(subject)

            if issuedate is None:
                self.logger.warning('Unable to get issue date from %s', subject)
                continue

            if issuedate != dateobj:
                continue

            reobj = re.match('^no(\.)?[_ ]+(?P<num>\d+).*$', subject, flags=re.IGNORECASE)
            if reobj is None:
                self.logger.warning('Unable to get gazette number from %s, %s', subject, metainfo)
                continue

            g = reobj.groupdict()
            newmeta['gznum']   = g['num'].strip()
            newmeta['subject'] = main_subject
            newmeta.set_date(dateobj)

            if not newmeta['gznum']:
                continue

            relurl = os.path.join(relpath, newmeta['gznum'])
            if self.save_gazette(relurl, gzurl, newmeta):
                relurls.append(relurl)
        return relurls


    def download_onetype(self, dls, relpath, dateobj, url, gztype):
        pagenum = 1
        response = self.download_url_cached(url)
        while response is not None and response.webpage is not None:
            curr_url = response.response_url
            metainfos, nextpage = self.parse_results(response.webpage, curr_url, pagenum)

            for metainfo in metainfos:
                relurls = self.download_metainfo(relpath, metainfo, curr_url, dateobj, gztype)
                dls.extend(relurls)

            if nextpage is None:
                break

            pagenum += 1
            nexturl = urllib.parse.urljoin(curr_url, nextpage['href'])
            response = self.download_url_cached(nexturl)


class AssamExtraOrdinary(AssamBase):
    def __init__(self, name, storage):
        AssamBase.__init__(self, name, storage)
        self.gztype = 'Extraordinary'
    
    def download_oneday(self, relpath, dateobj):
        dls = []
        year = dateobj.year

        extraordinary_urls_by_year = self.get_yearly_links(self.gztype)

        extraordinary_urls = [ extraordinary_urls_by_year.get(str(year - 1), None), \
                               extraordinary_urls_by_year.get(str(year), None), \
                               extraordinary_urls_by_year.get(str(year + 1), None) ]

        for extraordinary_url in extraordinary_urls:
            if extraordinary_url is not None:
                self.download_onetype(dls, relpath, dateobj, extraordinary_url, self.gztype)

        return dls

class AssamWeekly(AssamBase):
    def __init__(self, name, storage):
        AssamBase.__init__(self, name, storage)
        self.gztype = 'Weekly'
    
    def download_oneday(self, relpath, dateobj):
        dls = []
        year = dateobj.year

        ordinary_urls_by_year = self.get_yearly_links(self.gztype)

        ordinary_url = ordinary_urls_by_year.get(str(year), None)

        if ordinary_url is not None:
            self.download_onetype(dls, relpath, dateobj, ordinary_url, self.gztype)

        return dls