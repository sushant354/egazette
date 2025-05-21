import urllib.request, urllib.parse, urllib.error

from ..utils import utils
from ..utils import decode_captcha
from .haryana import Haryana

class Himachal(Haryana):
    def __init__(self, name, storage):
        Haryana.__init__(self, name, storage)
        self.hostname = 'rajpatrahimachal.nic.in'
        self.baseurl  = 'http://rajpatrahimachal.nic.in/Default.aspx'
        self.search_endp = 'Default.aspx'
        self.result_table = 'GVNotification'
        self.captcha_field = 'searchtext'
        self.solve_captcha = decode_captcha.himachal
        self.search_button = 'BtnSearch'

    def get_post_data(self, tags, dateobj):
        datestr  = utils.dateobj_to_str(dateobj, '/', reverse = False)
        postdata = []

        radio_set = False
        for tag in tags:
            name  = None
            value = None

            if tag.name == 'input':
                name  = tag.get('name')
                value = tag.get('value')
                t     = tag.get('type')
                if t == 'image':
                    continue
                if name == 'BtnElectronicGazette':
                    continue
                        
                if name == 'RBLanguage' \
                        and radio_set:
                    continue

                if name == 'GMDatePicker1$ctl00' or \
                        name == 'GMGazzetteDate$ctl00':
                    value = datestr
                elif name == 'RBLanguage':
                    value = 'Both'
                    radio_set = True
            elif tag.name == 'select':
                name = tag.get('name')
                if name == 'BtnSearch':
                    value = 'Search'
                elif name == 'DDListCategory':
                    value = ''
                elif name == 'DDListDepartment':
                    value = ''

            if name:
                if value == None:
                    value = ''
                postdata.append((name, value))
        return postdata
        
    def download_captcha(self, search_url, webpage, cookiejar):
        d = utils.parse_webpage(webpage, self.parser)
        if d == None:
            return None

        imgs = d.find_all('img')
        for img in imgs:
            src = img.get('src')
            if src and src.find('CaptchaImage.axd') >= 0:
                captcha_url = urllib.parse.urljoin(search_url, src)
                return self.download_url(captcha_url, loadcookies=cookiejar)
        return None
