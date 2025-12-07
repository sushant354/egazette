import re
import os
import urllib.parse
from http.cookiejar import CookieJar
import datetime
from io import BytesIO

from ..utils import utils
from .basegazette import BaseGazette

class Karnataka(BaseGazette):
    def __init__(self, name, storage):
        BaseGazette.__init__(self, name, storage)

        self.baseurl    = 'http://www.gazette.kar.nic.in/%s/'
        self.hostname   = 'www.gazette.kar.nic.in'
        self.flip_date1 = datetime.date(2009, 0o3, 0o5)
        self.flip_date2 = datetime.date(2013, 0o3, 0o7)

    def download_oneday(self, relpath, dateobj):
        dls = []
        if dateobj >= self.flip_date1:
            if dateobj >= self.flip_date2:
                datestr = '%d-%d-%d' % (dateobj.day, dateobj.month, dateobj.year)
            else:
                datestr = '%s-%s-%d' % (utils.pad_zero(dateobj.day), utils.pad_zero(dateobj.month), dateobj.year)
            mainhref = 'Contents-(%s).pdf' % datestr
        else:
            datestr = utils.dateobj_to_str(dateobj, '', reverse=True)    
            mainhref = 'Contents(%s-%s-%s).pdf' % (utils.pad_zero(dateobj.day), utils.pad_zero(dateobj.month), utils.pad_zero(dateobj.year % 100))

        dateurl = self.baseurl % datestr
        docurl  = urllib.parse.urljoin(dateurl, mainhref)

        mainmeta = utils.MetaInfo()
        mainmeta.set_date(dateobj)
        mainmeta.set_url(self.url_fix(docurl))
       
        response = self.download_url(docurl)
        if not response or not response.webpage or response.error:
            return dls

        mainrelurl = os.path.join(relpath, 'main')
        updated = False
        if self.storage_manager.save_rawdoc(self.name, mainrelurl, response.srvresponse, response.webpage):
            self.logger.info('Saved rawfile %s' % mainrelurl)
            updated = True


        page_type = self.get_file_extension(response.webpage)
        if page_type != 'pdf':
            self.logger.warning('Got a non-pdf page and we can\'t handle it for datte %s', dateobj)
            return dls

        links = []
        linknames = []
        hrefs = utils.extract_links_from_pdf(BytesIO(response.webpage))
        for href in hrefs:
            reobj = re.search('(?P<num>Part-\w+)', href)
            if reobj:
                partnum = reobj.groupdict()['num']
            else:
                partnum = '%s' % href
                reobj = re.search('.pdf$', partnum)
                if partnum:
                    partnum = partnum[:reobj.start()]
                 
            relurl = os.path.join(relpath, partnum)
            docurl = urllib.parse.urljoin(dateurl, href) 

            metainfo = utils.MetaInfo()
            metainfo.set_date(dateobj)
            metainfo['partnum'] = partnum

            links.append(relurl)
            linknames.append(partnum)

            if self.save_gazette(relurl, docurl, metainfo):
                dls.append(relurl)

        mainmeta['links']     = links
        mainmeta['linknames'] = linknames
        if self.storage_manager.save_metainfo(self.name, mainrelurl, mainmeta):
            updated = True
            self.logger.info('Saved metainfo %s' % mainrelurl)

        if updated:    
            dls.append(mainrelurl)

        return dls
       
class KarnatakaBase(BaseGazette):
    def __init__(self, name, storage):
        BaseGazette.__init__(self, name, storage)
        self.baseurl = 'https://erajyapatra.karnataka.gov.in'
        self.hostname = 'erajyapatra.karnataka.gov.in'
        self.curr_url = self.baseurl,
        self.search_url = self.baseurl
        self.search_endp = 'Search1.aspx'
        self.category_field = 'ctl00$ContentPlaceHolder1$ddlcate'
        self.table_field = 'ContentPlaceHolder1_dgGeneralUser'
        self.cookiejar = CookieJar()
        self.gztype = ''
       
    def extract_post_data(self, d):
        post_data = {}

        fields = [
            '__VIEWSTATE',
            '__EVENTVALIDATION',
            '__LASTFOCUS',
            '__VIEWSTATEGENERATOR',
            '__SCROLLPOSITIONX',
            '__SCROLLPOSITIONY',
            '__VIEWSTATEENCRYPTED',
            'ctl00$ContentPlaceHolder1$hidden1',
            'ctl00$ContentPlaceHolder1$hidden2',
            '__EVENTARGUMENT'
        ]

        for name in fields:
            elem = d.find('input', {'name': name})
            if elem and elem.has_attr('value'):
                post_data[name] = elem['value']

        return post_data
  
    def get_gazette_post_data(self):
        post_data = {}
        response = self.download_url(self.search_url, savecookies= self.cookiejar, \
                                     loadcookies= self.cookiejar, referer=self.search_url)
        if not response or not response.webpage or response.error:
            self.logger.warning('Could not fetch post data from %s', self.search_url)
            return post_data
        
        self.curr_url = response.response_url
        self.search_url = urllib.parse.urljoin(self.curr_url, self.search_endp)
        d = utils.parse_webpage(response.webpage, self.parser)
        if not d:
            return post_data

        post_data = self.extract_post_data(d)
        post_data['__EVENTTARGET'] = self.category_field
        return post_data
    
    def get_additional_payload(self, d):
        post_data = {}
        fields = [
            'ctl00$ContentPlaceHolder1$ddlministry',
            'ctl00$ContentPlaceHolder1$ddlSubMinistry',
            'ctl00$ContentPlaceHolder1$ddldepartment',
        ]

        for name in fields:
            select_elem = d.find('select', {'name': name})

            if select_elem:
                selected_opt = select_elem.find('option', selected=True)
                if selected_opt and selected_opt.has_attr('value'):
                    value = selected_opt['value'].strip()
                    post_data[name] = value

        btn_elem = d.find('input', {'name': 'ctl00$ContentPlaceHolder1$btndet'})
        if btn_elem and btn_elem.has_attr('value'):
            post_data['ctl00$ContentPlaceHolder1$btndet'] = btn_elem['value'].strip()

        return post_data

    def build_search_payload(self, dateobj, postdata):
        formatted_date = dateobj.strftime('%d-%b-%Y')
        post_data = {}
        response = self.download_url(self.search_url, postdata= postdata, \
                                     savecookies= self.cookiejar, loadcookies= self.cookiejar, 
                                     encodepost=True, referer=self.search_url)
        if not response or not response.webpage or response.error:
            self.logger.warning('Could not fetch gazette types from %s', self.search_url)
            return  post_data
        
        self.curr_url = response.response_url
        self.search_url = urllib.parse.urljoin(self.curr_url, self.search_endp)
        d = utils.parse_webpage(response.webpage, self.parser)
        if not d:
            return  post_data
        
        post_data['__EVENTTARGET'] = ''
        post_data['ctl00$ContentPlaceHolder1$txtDateIssueF'] = formatted_date
        post_data['ctl00$ContentPlaceHolder1$txtDateIssueT'] = formatted_date
        post_data.update(self.extract_post_data(d))
        post_data.update(self.get_additional_payload(d))
        return post_data
        
    def get_pdf_payload(self, webpage, dateobj):
        formatted_date = dateobj.strftime('%d-%b-%Y')
        post_data = {} 
        d = utils.parse_webpage(webpage, self.parser)
        if not d:
            return  post_data
        
        post_data['__EVENTTARGET'] = ''
        post_data['ctl00$ContentPlaceHolder1$txtDateIssueF'] = formatted_date
        post_data['ctl00$ContentPlaceHolder1$txtDateIssueT'] = formatted_date
        post_data.update(self.extract_post_data(d))
        post_data.update(self.get_additional_payload(d))
        return post_data
    
    def download_oneday(self, relpath, dateobj):
        dls = []
        response = self.download_url(self.baseurl, savecookies= self.cookiejar)
        if not response:
            self.logger.warning('Could not fetch %s for the day %s', self.baseurl, dateobj)
            return dls

        self.curr_url = response.response_url
        self.search_url = urllib.parse.urljoin(self.curr_url, self.search_endp)
        
        postdata = self.get_gazette_post_data()
        if not postdata:
            return dls

        
        postdata['ctl00$ContentPlaceHolder1$ddlcate'] = self.gztype
        payload = self.build_search_payload(dateobj, postdata)
        payload['ctl00$ContentPlaceHolder1$ddlcate'] = self.gztype
        response = self.download_url(self.search_url, postdata=payload, savecookies= self.cookiejar, \
                                        loadcookies= self.cookiejar, referer=self.search_url, \
                                    encodepost= True)
        if not response or not response.webpage or response.error:
            return dls

        self.curr_url = response.response_url
        self.search_url = urllib.parse.urljoin(self.curr_url, self.search_endp)
        payload_for_pdf = self.get_pdf_payload(response.webpage, dateobj)
        metainfos = self.process_search_results(response.webpage)

        if not metainfos:
            return dls
        
        for metainfo in metainfos:
            metainfo.set_date(dateobj)
            metainfo.set_gztype(self.gztype)
            dls1 = self.download_gazette(payload_for_pdf, metainfo, relpath)
            if dls1:
                dls.append(dls1)
        return dls
    
    def download_gazette(self, payload, metainfo, relpath):
        if 'download' in metainfo:
                newpost = dict(payload)
                name = metainfo.pop('download')
                newpost['%s.x' % name] = '6'
                newpost['%s.y' % name] = '12'
                newpost.pop('ctl00$ContentPlaceHolder1$btndet')
                relurl = os.path.join(relpath,metainfo.get_refnum())
                if self.save_gazette(relurl, self.search_url, metainfo = metainfo,\
                                     postdata = newpost,\
                                    referer= self.search_url ,cookiefile =  self.cookiejar):
                    return relurl
                
    def get_column_order(self, tr):
        order = []

        for td in tr.find_all('td'):
            txt = utils.get_tag_contents(td)

            if txt and re.search('ಕ್ರ.ಸಂ.', txt):
                order.append('cr.the no.')
            elif txt and re.search('ಇಲಾಖೆ / ಸಂಸ್ಥೆ', txt):
                order.append('department/institution')
            elif txt and re.search('ಇಲಾಖೆ', txt):
                order.append('department')
            elif txt and re.search('ಕಚೇರಿ', txt):
                order.append('office')
            elif txt and re.search('ವಿಷಯ', txt):
                order.append('subject')
            elif txt and re.search('ಸಂಚಿಕೆ ದಿನಾಂಕ', txt):
                order.append('issuedate')
            elif txt and re.search('ಭಾಗ', txt):
                order.append('part')
            elif txt and re.search('ಉಲ್ಲೇಖ ಸಂಖ್ಯೆ', txt):
                order.append('the number of reference')
            elif txt and re.search('ಡೌನ್‌ಲೋಡ್ ಮಾಡಿ', txt):
                order.append('download')
            else:
                order.append('')

        return order
    
    def process_result_row(self, tr, metainfos, order):
        metainfo = utils.MetaInfo()
        metainfos.append(metainfo)

        i  = 0
        for td in tr.find_all('td'):
            if len(order) > i:
                col = order[i]
                txt = utils.get_tag_contents(td)
                if txt:
                    txt = txt.strip()

                if col == 'department/institution':
                    metainfo.set_ministry(txt)
                elif col == 'subject':
                    metainfo.set_subject(txt)
                elif col == 'part':
                    metainfo.set_partnum(txt)
                elif col == 'the number of reference':
                    metainfo.set_refnum(txt)
                elif col == 'download':
                    inp = td.find('input')
                    if inp:
                        name = inp.get('name')
                        if name:
                            metainfo[col] = name
                    else:
                        link = td.find('a')
                        if link:
                            metainfo[col] = link 
                                            
                elif col in ['office', 'department']:
                    metainfo[col] = txt
            i += 1
    
    def get_metainfos(self, table):
        metainfos = []
        order = None
        for tr in table.find_all('tr'):
            if not order:
                order = self.get_column_order(tr)
                continue

            self.process_result_row(tr, metainfos, order)

        return metainfos

    def process_search_results(self, webpage):
        metainfos = []
        d = utils.parse_webpage(webpage, self.parser)
        if not d:
            return metainfos
        
        table = d.find('table', {'id': self.table_field})
        if not table:
            self.logger.warning('Couldn\'t find the table')
            return metainfos
        
        metainfos = self.get_metainfos(table)
        return metainfos

class KarnatakaExtraOrdinary(KarnatakaBase):
    def __init__(self, name, storage):
        KarnatakaBase.__init__(self, name, storage)
        self.gztype = 'Extra Ordinary'

class KarnatakaWeekly(KarnatakaBase):
    def __init__(self, name, storage):
        KarnatakaBase.__init__(self, name, storage)
        self.gztype = 'Weekly'

class KarnatakaDaily(KarnatakaBase):
    def __init__(self, name, storage):
        KarnatakaBase.__init__(self, name, storage)
        self.gztype = 'Daily'