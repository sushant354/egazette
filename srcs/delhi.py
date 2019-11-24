import datetime

from .central import CentralWeekly
from ..utils import utils

class DelhiWeekly(CentralWeekly):
    def __init__(self, name, storage):
        CentralWeekly.__init__(self, name, storage)
        self.baseurl     = 'http://www.egazette.nic.in/SG_DL_Search.aspx'
        self.search_endp = 'SG_DL_Search.aspx'
        self.result_table = 'dgGeneralUser'
        self.start_date   = datetime.datetime(2016, 5, 1)

    def get_post_data(self, tags, dateobj):
        datestr  = utils.get_egz_date(dateobj)
        postdata = []

        for tag in tags:
            name  = None
            value = None

            if tag.name == 'input':
                name  = tag.get('name')
                value = tag.get('value')
                t     = tag.get('type')
                if t == 'image' or name in ['btn_Reset', 'hidden2', 'hidden1']:
                    continue

                if name == 'btnstd':
                    value = 'Search' 

                if name == 'txtDateIssueF' or name == 'txtDateIssueT':
                    value = datestr
            elif tag.name == 'select':        
                name = tag.get('name')
                if name == 'ddlcate':
                    value = self.gztype
                elif name == 'ddlPartSection':
                    value = 'Select Part & Section'
            if name:
                if value == None:
                    value = ''
                postdata.append((name, value))

        return postdata


class DelhiExtraordinary(DelhiWeekly):
    def __init__(self, name, storage):
        DelhiWeekly.__init__(self, name, storage)
        self.gztype   = 'Extra Ordinary'


