import re
import os
import time
import json
import copy
import base64
import urllib.parse
from http.cookiejar import CookieJar

import requests
import urllib3
import ssl

from ..utils import utils
from .basegazette import BaseGazette

default_ssl_context_creator = ssl._create_default_https_context

def legacy_negotiation_enabled_context_creator(*args, **kwargs):
    ctx = default_ssl_context_creator(*args, **kwargs)
    ctx.options |= 0x4  # OP_LEGACY_SERVER_CONNECT
    return ctx

ssl._create_default_https_context = legacy_negotiation_enabled_context_creator
    
class CustomHttpAdapter(requests.adapters.HTTPAdapter):
    # "Transport adapter" that allows us to use custom ssl_context.

    def __init__(self, ssl_context=None, **kwargs):
        self.ssl_context = ssl_context
        super().__init__(**kwargs)

    def init_poolmanager(self, connections, maxsize, block=False):
        self.poolmanager = urllib3.poolmanager.PoolManager(
            num_pools=connections, maxsize=maxsize,
            block=block, ssl_context=self.ssl_context)

class DelayedRetryException(Exception):
    pass
 
class RajasthanBase(BaseGazette):
    def __init__(self, name, storage):
        BaseGazette.__init__(self, name, storage)
        self.baseurl = 'https://reams.rajasthan.gov.in'
        self.hostname = 'reams.rajasthan.gov.in'
        self.gztype  = ''


    def get_post_data(self, tags, dateobj):
        postdata = []

        for tag in tags:
            name  = None
            value = None

            if tag.name == 'input':
                name  = tag.get('name')
                value = tag.get('value')
                t     = tag.get('type')

                if t == 'button':
                    continue
                if name == 'selMetaDataType':
                    continue
                if name == 'ControlsList[0].value':
                    value = dateobj.strftime('%d-%m-%Y')

            elif tag.name == 'select':
                name = tag.get('name')
                value = utils.get_selected_option(tag)
            if name:
                if value is None:
                    value = ''
                postdata.append((name, value))

        return postdata

    def get_form_data(self, webpage, dateobj):
        search_form = utils.get_search_form(webpage, self.parser, '/PrintingStationary/GuestSearch')
        if search_form is None:
            self.logger.warning('Unable to get search form for date: %s', dateobj)
            return None

        reobj  = re.compile('^(input|select)$')
        inputs = search_form.find_all(reobj)

        postdata = self.get_post_data(inputs, dateobj)

        return postdata

    def select_option(self, select, section_re):
        for option in select.find_all('option'):
            txt = utils.get_tag_contents(option)
            reobj = re.search(section_re, txt)
            if reobj:
                return option.get('value')

        return None

    def get_citizen_post_data(self, tags, dateobj, section_re):
        postdata = []

        for tag in tags:
            name  = None
            value = None

            if tag.name == 'input':
                name  = tag.get('name')
                value = tag.get('value')
                t     = tag.get('type')

                if t == 'button' or t == 'submit':
                    continue
                if name in [ '_OrdinaryMetaData.FromDate', '_OrdinaryMetaData.ToDate' ]:
                    value = dateobj.strftime('%m/%d/%Y')

            elif tag.name == 'select':
                name = tag.get('name')
                if name == '_OrdinaryMetaData.TemplateID':
                    value = self.select_option(tag, section_re)
            if name:
                if value is None:
                    value = ''
                postdata.append((name, value))

        return postdata

    def get_citizen_form_data(self, webpage, dateobj, section_re):
        search_form = utils.get_search_form(webpage, self.parser, '/PrintingStationary/GuestSearchOrdinaryCitizen')
        if search_form is None:
            self.logger.warning('Unable to get search form for date: %s', dateobj)
            return None

        reobj  = re.compile('^(input|select)$')
        inputs = search_form.find_all(reobj)

        postdata = self.get_citizen_post_data(inputs, dateobj, section_re)

        return postdata

    def get_citizen_column_order(self, tr):
        order = []
        for td in tr.find_all('th'):
            txt = utils.get_tag_contents(td)
            if txt and re.search(r'Application\s+Number', txt):
                order.append('application_num')
            elif txt and re.search(r'Requester\s+Name', txt):
                order.append('requester_name')
            elif txt and re.search(r'Amended\s+Name', txt):
                order.append('amended_name')
            elif txt and re.search(r'Amended\s+Type', txt):
                order.append('amended_type')
            elif txt and re.search(r'Firm\s+Name', txt):
                order.append('firm_name')
            elif txt and re.search(r'Notification\s+Number', txt):
                order.append('notification_num')
            elif txt and re.search(r'Volume\s+No', txt):
                order.append('volume_num')
            elif txt and re.search(r'Number', txt):
                order.append('gznum')
            elif txt and re.search(r'Action', txt):
                order.append('download')
            else:
                order.append('')
        return order

    def get_column_order(self, tr):
        order = []
        for td in tr.find_all('th'):
            txt = utils.get_tag_contents(td)
            if txt and re.search(r'Document\s+Category', txt):
                order.append('category')
            elif txt and re.search(r'Part\s+Number', txt):
                order.append('partnum')
            elif txt and re.search(r'Statutory\s+Notification\s+Number', txt):
                order.append('notification_num')
            elif txt and re.search(r'Sub\s+Department\s+Name', txt):
                order.append('subdepartment')
            elif txt and re.search(r'Department\s+Name', txt):
                order.append('department')
            elif txt and re.search(r'Document\s+Type', txt):
                order.append('document_type')
            elif txt and re.search(r'Document', txt):
                order.append('download')
            else:
                order.append('')
        return order

    def process_result_row(self, metainfos, tr, order, dateobj):
        metainfo = utils.MetaInfo()
        metainfo.set_date(dateobj)

        i = 0
        for td in tr.find_all('td'):
            if len(order) > i:
                col = order[i]

                txt = utils.get_tag_contents(td)
                if txt:
                    txt = txt.strip()
                if col == 'download':
                    form = td.find('form', {'method': 'POST'})
                    if form is not None:
                        docview_url = form.get('action')
                        metainfo['downloadurl'] = docview_url

                        download_postdata = []
                        for inp in form.find_all('input'):
                            name  = inp.get('name')
                            value = inp.get('value')
                            if name:
                                if value is None:
                                    value = ''
                                download_postdata.append((name, value))
                        metainfo['downloadpostdata'] = download_postdata
                elif col != '':
                    metainfo[col] = txt
            i += 1

        if 'downloadurl' in metainfo:
            metainfos.append(metainfo)

    def parse_search_results(self, webpage, dateobj, curr_page, get_column_order_fn):
        metainfos = []
        has_nextpage = False
        results_per_page = None

        d = utils.parse_webpage(webpage, self.parser)
        if not d:
            self.logger.warning('Unable to parse search result page for %s', dateobj)
            return metainfos, has_nextpage, results_per_page

        table = d.find('table', {'id': 'dataTable'})
        if table is None:
            self.logger.warning('Could not find the result table for %s', dateobj)
            return metainfos, has_nextpage, results_per_page

        order = None
        for tr in table.find_all('tr'):
            if not order:
                order = get_column_order_fn(tr)
                continue

            if tr.find('input') is None and tr.find('a') is None:
                continue

            self.process_result_row(metainfos, tr, order, dateobj)


        div = d.find('div', {'class': 'dataTables_paginate'})
        if div is None:
            self.logger.warning('Could not find pagination div node for %s', dateobj)
            return metainfos, has_nextpage, results_per_page

        for inp in div.find_all('input'):
            val = inp.get('value')
            if val:
                try: 
                    page_no = int(val)
                except Exception:
                    page_no = None
                if page_no == curr_page + 1:
                    has_nextpage = True
                    break

        select = d.find('select', {'id': 'PageSizeid'})
        if select is None:
            self.logger.warning('Could not find page size node for %s', dateobj)
            return metainfos, has_nextpage, results_per_page

        results_per_page = utils.get_selected_option(select)
        return metainfos, has_nextpage, results_per_page

    def encode_multiform_post(self, postdata):
        boundary = "----WebKitFormBoundaryecDC0QcQWcBRoF9a"
        payload = ''
        for key, value in postdata:
            payload += f'--{boundary}\r\nContent-Disposition: form-data; name="{key}"\r\n\r\n{value}\r\n'
        payload += f'--{boundary}--'
        headers = { 'Content-Type': f'multipart/form-data; boundary={boundary}' }
        return payload.encode('utf-8'), headers

    def download_nextpage(self, post_url, search_url, postdata, pagenum, results_per_page, cookiejar):
        newpost = []
        newpost.extend(postdata)
        newpost.append(('min', str(pagenum + 1)))
        newpost.append(('max', results_per_page))

        newpost_encoded, headers = self.encode_multiform_post(newpost)

        response = self.download_url(post_url, loadcookies = cookiejar, savecookies = cookiejar, \
                                     postdata = newpost_encoded, headers = headers, \
                                     encodepost = False, referer = search_url)

        return response


    def download_url_json(self, url, postdata, cookiejar, referer):
        postdata_encoded = json.dumps(postdata).encode('utf-8')
        headers = { 'Content-Type': 'application/json' }
        response = self.download_url(url, postdata = postdata_encoded, \
                                     encodepost = False, headers = headers, \
                                     loadcookies = cookiejar, savecookies = cookiejar,
                                     referer = referer)
        if not response or not response.webpage:
            self.logger.warning('Could not get response for %s', url)
            return None

        try:
            data = json.loads(response.webpage)
        except Exception:
            self.logger.warning('Unable to parse response for %s', url)
            return None

        return data

    def get_login_postdata(self, config, omnidocsuid):
        webapiconfig       = config['Response']['Configuration']['webApiConfiguration']
        connection_details = webapiconfig['connectionDetails']
        metadata           = webapiconfig['metaData']
        cabinetname        = webapiconfig['configurationSettings']['cabinetName']

        username       = connection_details['userName']
        password       = base64.b64encode(connection_details['password'].encode('utf-8')).decode('utf-8')
        externalOD_UID = connection_details['externalOD_UID']

        jtsip    = metadata['jtsIp']
        jtsport  = metadata['jtsPort']
        siteid   = metadata['siteId']
        dbtype   = metadata['dataBaseType']
        #folderid = metadata['folderId']

        return {
            'IsForceFully'        : "yes",
            'Mode'                : "",
            'cabinetName'         : f"{jtsip}${jtsport}${siteid}$None$,~{dbtype}~{cabinetname}",
            'externalLogin'       : False,
            'externalOD_UID'      : externalOD_UID,
            'isuserDbIdEncrypted' : False,
            'locale'              : "",
            'logOutUrl'           : "",
            'loginMethod'         : "",
            'omnidocsUID'         : omnidocsuid,
            'password'            : password,
            'userDbId'            : "",
            'userName'            : username,
            "webpage"             : "webApi"
        }

    def get_field(self, ident, name, logical_operator, operator, value, \
                  field_value="", data_type="", user_fields = False):
        field = {
            "CustomPickableFlag"     : "N",
            "PickListCustomUIURL"    : "",
            "PickListRestServiceURL" : "",
            "PickListType"           : "manual",
            "dataType"               : data_type,
            "date"                   : None,
            "end"                    : "",
            "endDate"                : None,
            "fieldType"              : None,
            "fieldValue"             : field_value,
            "id"                     : ident,
            "imagesrc"               : "",
            "isPickable"             : False,
            "localisedName"          : "",
            "logicalOperator"        : logical_operator,
            "name"                   : name,
            "operator"               : operator,
            "picklist"               : [],
            "rights"                 : [],
            "selectedPicklistValueMetaData" : [],
            "start"                  : "",
            "startDate"              : None,
            "uploadIconName"         : "",
            "urlToOpen"              : "",
            "validValue"             : True,
            "value"                  : value,
        }
        for access_type in [ "Read", "Annotate", "Modify", "Delete", "Print", "Copy", "View Secure Data" ]:
            field["rights"].append({ "id" : access_type, "checked": access_type == "Read" })

        if user_fields:
            field["groupId"]      = ""
            field["groupName"]    = ""
            field["originalName"] = ""
            field["userId"]       = ""
            field["userName"]     = ""
            field["userType"]     = ""
            field["filterUserByGroupEnabled"] = False

        return field

    def get_searchdoc_postdata(self, doc_data, prop_data, dataclassid):
        postdata = {
            "currentBatch"          : 1,
            "customSortClass"       : "",
            "customSortMethod"      : "",
            "enableLogicalOperator" : False,
            "encryptedFields"       : "",
            "executeCustomSort"     : False,
            "ftsAS"                 : False,
            "ftsIS"                 : False,
            "ftsSearchText"         : "",
            "ftsType"               : "FTSIS",
            "generateReport"        : "false",
            "includeAllVersions"    : False,
            "includeFullTextSearch" : False,
            "includeSubFolder"      : True,
            "includereferences"     : "B",
            "isEncryptedFields"     : "",
            "inputFields"           : {
                "advanceSetting"        : False,
                "advanceSettingGI"      : False,
                "checkoutByUsername"    : "",
                "checkoutStatus"        : "", 
                "dataClass"             : {
                    "dataClassFields"        : [],
                    "dataClassId"            : dataclassid,
                    "dataClassName"          : doc_data['DataClassName'],
                    "localisedDataClassName" : "",
                    "sortDDTField"           : "N",
                },
                "date"                  : [],
                "enableAllDataClassesField" : False,
                "general"               : [],
                "globalIndex"           : [],
                "keywords"              : [],
            },
            "lookInFolderName"      : "",
            "lookinfolderid"        : 0,
            "maxHitCount"           : False,
            "name"                  : "",
            "prevDocIndex"          : 0,
            "result"                : {
                "operationsOnDocument"  : [],
                "operationsOnFolder"    : [],
                "outputField"           : [],
            },
            "settings"              : {
                "batchSize"             : "10",
                "docViewProp"           : [],
                "docViewToolBarProp"    : [],
                "groups"                : [],
                "sortOn"                : {},
                "sortOrder"             : "Descending",
                "zoomPercentage"        : "FitToPage",
            },
            "showPath"              : "",
            "thumbnailAlso"         : False,
            "type"                  : "Document",
        }


        postdata["inputFields"]["date"].append(self.get_field("CreatedDate", "Created Date", "", "All", False))
        postdata["inputFields"]["date"].append(self.get_field("ModifiedDate", "Modified Date", "", "All", False))

        postdata["inputFields"]["general"].append(self.get_field("GENERAL_FIELD_NAME", "Name", "AND", "", True))
        postdata["inputFields"]["general"].append(self.get_field("GENERAL_FIELD_OWNER", "Owner", "AND", "", False, user_fields = True))
        postdata["inputFields"]["general"].append(self.get_field("GENERAL_FIELD_TYPE", "Type", "AND", "", False))
        postdata["inputFields"]["general"].append(self.get_field("GENERAL_FIELD_SIZE", "Size", "AND", "", False))
        postdata["inputFields"]["general"].append(self.get_field("GENERAL_FIELD_KEYWORDS", "Keywords", "AND", "", False))
        postdata["inputFields"]["general"].append(self.get_field("GENERAL_FIELD_CREATION_DATE", "CreatedDate", "AND", "equals", False))
        postdata["inputFields"]["general"].append(self.get_field("GENERAL_FIELD_MODIFIED_DATE", "ModifiedDate", "AND", "equals", False))
        postdata["inputFields"]["general"].append(self.get_field("GENERAL_FIELD_ACCESSED_DATE", "AccessedDate", "AND", "equals", False))

        postdata["result"]["operationsOnDocument"].append(self.get_field("-1", "", "", "", True))
        postdata["result"]["operationsOnFolder"].append(self.get_field("-1", "", "", "", True))

        postdata["settings"]["sortOn"] = self.get_field("ModifiedDate", "ModifiedDate", "", "", True)

        prop_data_dict = { e['IndexName']: e for e in prop_data }
        to_add = {}
        to_add.update(doc_data)
        to_add['DC.Param6'] = ""
        for k,v in doc_data.items():
            if not k.startswith("DC."):
                continue
            k = k[3:]
            prop_values = prop_data_dict[k]
            postdata["inputFields"]["dataClass"]["dataClassFields"].append(self.get_field(prop_values["IndexId"], k, "AND", "equals", True, \
                                                                                          field_value = v, data_type = prop_values['IndexType']))

        return postdata
        

    def get_download_postdata(self, search_doc_data, config, login_data):
        webapiconfig = config['Response']['Configuration']['webApiConfiguration']
        metadata     = webapiconfig['metaData']
        cabinetname  = webapiconfig['configurationSettings']['cabinetName']

        jtsip    = metadata['jtsIp']
        jtsport  = metadata['jtsPort']
        siteid   = metadata['siteId']

        userdbid = login_data[1]['UserDbId']

        docid    = search_doc_data[1]['DocumentIndex']
        docname  = search_doc_data[1]['DocumentName']
        #folderid = search_doc_data[1]['ParentFolderIndex']
        docuserrights = search_doc_data[1]['LoginUserRights']

        
        query_params = [
            ('ImgCabinetName', cabinetname),
            ('ImageId', ''),
            ('DocId', docid),
            ('DocumentName', docname),
            ('PageNo', '1'),
            ('docExt', 'PDF'),
            ('Option', 'Download'),
            ('docType', 'N'),
            ('UserDbId', userdbid),
            ('Encoding', 'UTF-8'),
            ('isWebAccess', 'Y'),
            ('VersionNo', ''),
            ('docUserRights', docuserrights),
            ('Docuri', ''),
        ]

        postdata = [
            ('Option', 'Download'),
            ('ImgCabinetName', cabinetname),
            ('JtsIpAdd', jtsip),
            ('JtsIpPort', jtsport),
            ('VolId', ''),
            ('SiteId', siteid),
            ('ImageId', ''),
            ('PageNo', '1'),
            ('DocId', docid),
            ('docExt', 'PDF'),
            ('DocumentName', docname),
            ('isWebAccess', 'Y'),
            ('docType', 'N'),
            ('Encoding', 'UTF-8'),
            ('UserDbId', userdbid),
            ('docUserRights', ''), 
            ('VersionNo', ''), 
            ('Docuri', ''), 
        ]
        return query_params, postdata
    
    def get_session(self):
        ctx = ssl.create_default_context(ssl.Purpose.SERVER_AUTH)
        ctx.options |= 0x4  # OP_LEGACY_SERVER_CONNECT
        session = requests.session()
        retry = self.get_session_retry()
        session.mount('https://', CustomHttpAdapter(ctx, max_retries=retry))
        return session

    def download_metainfo_wrapped(self, relpath, metainfo, gztype): 
        while True:
            try:
                return self.download_metainfo(relpath, metainfo, gztype)
            except DelayedRetryException:
                time.sleep(300)


    def pull_gazette(self, gurl, referer = None, postdata = None,
                     cookiefile = None, headers = {}, \
                     encodepost = True):

        postdata_dict = dict(postdata)
        docview_url   = gurl
       
        #cabinetname   = postdata_dict['cabinetName']
        dataclassname = postdata_dict['DataClassName']

        cookiejar = CookieJar()
        session = self.get_session()
        session.cookies = cookiejar
        response = self.download_url_using_session(docview_url, postdata = postdata, \
                                                   session = session, referer = self.baseurl, \
                                                   allow_redirects = False)

        if response is None or response.srvresponse is None:
            self.logger.warning('Unable to get page %s', docview_url)
            return None

        if response.srvresponse['status'] != 302:
            self.logger.warning('Unexpected status while getting page %s', docview_url)
            return None

        redirect_url = response.srvresponse['headers']['Location']
        redirect_url = redirect_url.replace('http://', 'https://')

        parsed            = urllib.parse.urlparse(redirect_url)
        frag_parsed       = urllib.parse.urlparse(parsed.fragment)
        frag_parsed_query = urllib.parse.parse_qs(frag_parsed.query)
        omnidocsuid       = frag_parsed_query['OD_UID'][0]

        parsed_cleaned    = parsed._replace(query=None, fragment=None)
        redirect_url_base = parsed_cleaned.geturl()

        config_url = urllib.parse.urljoin(redirect_url, '../GetWebApiConfiguration?OD_UID=')
        config_postdata = {
            'ApplicationName'   : postdata_dict['Application'],
            'CabinetName'       : postdata_dict['cabinetName'],
            'ConfigurationType' : "WebApiConfiguration",
        }
        config = self.download_url_json(config_url, config_postdata, cookiejar, redirect_url_base)
        if config is None:
            return None

        login_url = urllib.parse.urljoin(redirect_url, '../LoginServlet?OD_UID=')
        login_postdata = self.get_login_postdata(config, omnidocsuid)
        login_data = self.download_url_json(login_url, login_postdata, cookiejar, redirect_url_base)
        if login_data is None or len(login_data) != 2:
            self.logger.warning('Unable to login for docview')
            raise DelayedRetryException()

        def get_controller_url(funcname):
            return urllib.parse.urljoin(redirect_url, f'../ControllerServlet?requestCall={funcname}&OD_UID={omnidocsuid}')

        dataclass_search_url = get_controller_url('Component.DataClass.SearchDataClass')
        dataclass_search_postdata = { 'dataDefName' : dataclassname }
        dataclassid_data = self.download_url_json(dataclass_search_url, dataclass_search_postdata, \
                                                  cookiejar, redirect_url_base)
        if dataclassid_data is None:
            self.logger.warning('Unable to get dataclass id')
            return None

        dataclassid = dataclassid_data['DataDefIndex']

        dataclass_prop_url = get_controller_url('Component.omniProcessWizard.DataClassProperty')
        dataclass_prop_postdata = { 'DCIndex': { 'dataclassIndex': dataclassid } }
        dataclass_props = self.download_url_json(dataclass_prop_url, dataclass_prop_postdata, \
                                                 cookiejar, redirect_url_base)
        if dataclass_props is None:
            self.logger.warning('Unable to get dataclass properties for %s')
            return None

        search_doc_url = get_controller_url('Component.SearchConfiguration.SearchDocument')
        search_doc_postdata = self.get_searchdoc_postdata(postdata_dict, dataclass_props, dataclassid)
        search_doc_data = self.download_url_json(search_doc_url, search_doc_postdata, \
                                                 cookiejar, redirect_url_base)
        if search_doc_data is None or len(search_doc_data) < 2:
            self.logger.warning('Unable to search for doc')
            return None

        download_query_params, download_postdata = self.get_download_postdata(search_doc_data, config, login_data)
        download_url = urllib.parse.urljoin(redirect_url, '../servlet/getdocstream')
        download_url += '?'
        download_url += urllib.parse.urlencode(download_query_params)

        return BaseGazette.pull_gazette(self, download_url, postdata = download_postdata, \
                                        cookiefile = cookiejar, referer = redirect_url_base, \
                                        encodepost = encodepost, headers = headers)


    def download_metainfo(self, relpath, metainfo, gztype): 
        metainfo = copy.deepcopy(metainfo)
        metainfo.set_gztype(gztype)
        docview_url = metainfo.pop('downloadurl')
        postdata    = metainfo.pop('downloadpostdata')

        postdata_dict = dict(postdata)

        docid = postdata_dict['DC.DocumentID']
        relurl = os.path.join(relpath, docid)
        if self.save_gazette(relurl, docview_url, metainfo, \
                             postdata = postdata, validurl = False):
            return relurl

        return None


    def download_onetype(self, dls, relpath, dateobj, search_url, gztype):
        cookiejar  = CookieJar()

        response = self.download_url(search_url, savecookies = cookiejar)
        if response is None or response.webpage is None:
            self.logger.warning('Unable to get page %s for type %s and date %s', search_url, gztype, dateobj)
            return dls
    
        search_postdata = self.get_form_data(response.webpage, dateobj)
        if search_postdata is None:
            self.logger.warning('Unable to get form date from page %s for type %s and date %s', search_url, gztype, dateobj)
            return dls

        post_url = urllib.parse.urljoin(search_url, './Search')

        search_postdata_encoded, headers = self.encode_multiform_post(search_postdata)
        response = self.download_url(post_url, loadcookies = cookiejar, savecookies = cookiejar, \
                                     postdata = search_postdata_encoded, headers = headers, \
                                     encodepost = False, referer = search_url)

        pagenum = 1
        while response is not None and response.webpage is not None:
            metainfos, has_nextpage, results_per_page  = self.parse_search_results(response.webpage, \
                                                                                   dateobj, pagenum, \
                                                                                   self.get_column_order)

            for metainfo in metainfos:
                relurl = self.download_metainfo_wrapped(relpath, metainfo, gztype)
                if relurl:
                    dls.append(relurl)

            if not has_nextpage:
                break

            response = self.download_nextpage(post_url, search_url, search_postdata, \
                                              pagenum, results_per_page, cookiejar)

            pagenum += 1

    def download_onesection(self, dls, relpath, dateobj, section_re, subject, search_url):
        cookiejar  = CookieJar()

        response = self.download_url(search_url, savecookies = cookiejar)
        if response is None or response.webpage is None:
            self.logger.warning('Unable to get page %s for type %s and date %s', search_url, self.gztype, dateobj)
            return
    
        search_postdata = self.get_citizen_form_data(response.webpage, dateobj, section_re)
        if search_postdata is None:
            self.logger.warning('Unable to get form date from page %s for type %s and date %s', search_url, self.gztype, dateobj)
            return

        post_url = search_url

        search_postdata_encoded, headers = self.encode_multiform_post(search_postdata)
        response = self.download_url(post_url, loadcookies = cookiejar, savecookies = cookiejar, \
                                     postdata = search_postdata_encoded, headers = headers, \
                                     encodepost = False, referer = search_url)

        pagenum = 1
        while response is not None and response.webpage is not None:
            metainfos, has_nextpage, results_per_page  = self.parse_search_results(response.webpage, \
                                                                                   dateobj, pagenum, \
                                                                                   self.get_citizen_column_order)

            for metainfo in metainfos:
                metainfo['document_type'] = subject
                metainfo['category']      = 'Notification'
                relurl = self.download_metainfo_wrapped(relpath, metainfo, self.gztype)
                if relurl:
                    dls.append(relurl)

            if not has_nextpage:
                break

            response = self.download_nextpage(post_url, search_url, search_postdata, \
                                              pagenum, results_per_page, cookiejar)

            pagenum += 1


    def download_ordinary_citizen(self, dls, relpath, dateobj, url):
        self.download_onesection(dls, relpath, dateobj, r'Citizen\s+Name\s+Change', 'Citizen Name Chnage', url)
        self.download_onesection(dls, relpath, dateobj, r'Partnership\s+Amendment', 'Partnership Amendment', url)
        self.download_onesection(dls, relpath, dateobj, r'Government\s+Employee\s+Name\s+Change', 'Government Employee Name Change', url)

class RajasthanExtraOrdinary(RajasthanBase):
    def __init__(self, name, storage):
        RajasthanBase.__init__(self, name, storage) 
        self.url = 'https://reams.rajasthan.gov.in/PrintingStationary/GuestSearch?Searchcategory=Extra Ordinary'
        self.gztype = 'Extraordinary'

    def download_oneday(self, relpath, dateobj):
        dls = []
        self.download_onetype(dls, relpath, dateobj, self.url, self.gztype)
        return dls

class RajasthanOrdinaryCitizen(RajasthanBase):
    def __init__(self, name, storage):
        RajasthanBase.__init__(self, name, storage)
        self.ordinary_citizen_search_url = 'https://reams.rajasthan.gov.in/PrintingStationary/GuestSearchOrdinaryCitizen'
        self.gztype = 'Ordinary'
    
    def download_oneday(self, relpath, dateobj):
        dls = []
        self.download_ordinary_citizen(dls, relpath, dateobj, self.ordinary_citizen_search_url)
        return dls
