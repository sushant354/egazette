import re
import datetime

from .andhra import Andhra
from ..utils import utils

class Telangana(Andhra):
    def __init__(self, name, storage):
        Andhra.__init__(self, name, storage)
        self.baseurl      = 'https://tsgazette.cgg.gov.in/viewGazette.do'
        self.hostname     = 'tsgazette.cgg.gov.in'
        self.searchurl    = self.baseurl
        self.start_date   = datetime.datetime(2014, 1, 1)

    def get_field_order(self, tr):
        i = 0
        order  = []
        valid = False
        for th in tr.find_all('th'):
            txt = utils.get_tag_contents(th)
            if txt and re.search('gazettetype', txt, re.IGNORECASE):
                order.append('gztype')
            elif txt and re.search('department', txt, re.IGNORECASE):
                order.append('department')
            elif txt and re.search('abstract', txt, re.IGNORECASE):
                order.append('subject')
            elif txt and re.search('Issue\s+No', txt, re.IGNORECASE):
                order.append('gznum')
            elif txt and re.search('Job\s+No', txt, re.IGNORECASE):
                order.append('job_num')
            elif txt and re.search('Download', txt, re.IGNORECASE):
                order.append('download')
                valid = True
            elif txt and re.search('', txt, re.IGNORECASE):
                order.append('')

            else:
                order.append('')    

            i += 1
        if valid:    
            return order
        return None    

    def get_post_data(self, dateobj):
        curr_date = utils.dateobj_to_str(datetime.date.today(), '/')
        datestr   = utils.dateobj_to_str(dateobj, '')

        postdata = [\
            ('displaytable_length',   '-1'), \
            ('mode',                  'unspecified'),  \
            ('property(abstract)',    ''  ), \
            ('property(docid)',       ''), \
            ('property(fromdate)',    datestr), \
            ('property(gazetteno)',   ''), \
            ('property(hdnCurDate)',  curr_date), \
            ('property(jobno)',       ''), \
            ('property(month1)',      '0'), \
            ('property(search)',      'searchGazette'), \
            ('property(searchmode)',  'date'), \
            ('property(todate)',      datestr), \
            ('property(year)',       '0'), \
            ('property(year1)',       '0'), \
        ]
        return postdata

    def parse_row(self, tr, order, dateobj):
        metainfo = utils.MetaInfo()
        metainfo.set_date(dateobj)

        i = 0
        for td in tr.find_all('td'):
            txt = utils.get_tag_contents(td)
            if i < len(order) and txt:
                txt = txt.strip()
                col = order[i]
                if col == 'gztype':
                    words = txt.split('/')
                    metainfo['gztype'] = words[0].strip()
                    if len(words) > 1:
                        metainfo['partnum'] = words[1].strip()
                    if len(words) > 2:
                        metainfo['district'] = words[2].strip()
                elif col == 'download':
                    inp = td.find('input')       
                    if inp and inp.get('onclick'): 
                        metainfo['download'] = inp.get('onclick')
                elif col in ['job_num', 'gznum', 'department']:
                    metainfo[col] = txt
                elif col == 'subject':
                    metainfo.set_subject(txt)    
            i += 1
        return metainfo

