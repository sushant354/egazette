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
  
class RajasthanStateArchive(BaseGazette):
    def __init__(self, name, storage):
        BaseGazette.__init__(self, name, storage)
        self.baseurl = 'https://reams.rajasthan.gov.in/RSAD/RSADGuestSearch'
        self.hostname = 'reams.rajasthan.gov.in'
    
    def get_session(self):
        ctx = ssl.create_default_context(ssl.Purpose.SERVER_AUTH)
        ctx.options |= 0x4  # OP_LEGACY_SERVER_CONNECT
        session = requests.session()
        retry = self.get_session_retry()
        session.mount('https://', CustomHttpAdapter(ctx, max_retries=retry))
        return session


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
        


    def get_city_list(self):
        city_list = []

        response = self.download_url(self.baseurl)
        if response is None or response.webpage is None:
            self.logger.warning('Unable to get page %s', self.baseurl)
            return city_list

        search_form = utils.get_search_form(response.webpage, self.parser, '/RSAD/RSADGuestSearch')

        if search_form is None:
            self.logger.warning('Unable to get search form')
            return city_list

        reobj  = re.compile('^(input|select)$')
        tags = search_form.find_all(reobj)

        for tag in tags:
            name = tag.get('name')
            if tag.name == 'select':
                if name == 'ControlsList[0].value':
                    for option in tag.find_all('option'):
                        oname = utils.get_tag_contents(option)
                        oval  = option.get('value')
                        if oval == "":
                            continue
                        city_list.append((oname, oval))

        return city_list

    def get_post_data(self, tags, city):
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
                #if name == 'selMetaDataType':
                #    continue

            elif tag.name == 'select':
                name = tag.get('name')
                if name == 'ControlsList[0].value':
                    value = city
                else:
                    value = utils.get_selected_option(tag)
            if name:
                if value is None:
                    value = ''
                postdata.append((name, value))

        return postdata


    def get_form_data(self, webpage, city):

        search_form = utils.get_search_form(webpage, self.parser, '/RSAD/RSADGuestSearch')

        d = utils.parse_webpage(webpage, self.parser)
        if not d:
            self.logger.warning('Unable to parse main page')
            return None

        if search_form is None:
            self.logger.warning('Unable to get search form')
            return None

        reobj  = re.compile('^(input|select)$')
        tags = search_form.find_all(reobj)

        postdata = self.get_post_data(tags, city)
        return postdata

    def get_column_order(self, thead):
        order = []
        for td in thead.find_all('th'):
            txt = utils.get_tag_contents(td)
            if txt and re.search(r'State/City/Other', txt):
                order.append('city')
            elif txt and re.search(r'Head/Topic', txt):
                order.append('topic')
            elif txt and re.search(r'Name\s+of\s+Department', txt):
                order.append('department')
            elif txt and re.search(r'Bahi\s+No', txt):
                order.append('bundleno')
            elif txt and re.search(r'Year', txt):
                order.append('year')
            elif txt and re.search(r'Description', txt):
                order.append('description')
            elif txt and re.search(r'File/Book\s+Name', txt):
                order.append('file')
            elif txt and re.search(r'Relevant\s+Office', txt):
                order.append('office')
            elif txt and re.search(r'Document', txt):
                continue
            elif txt and re.search(r'Main', txt):
                order.append('download')
            else:
                order.append('')
        return order


    def process_result_row(self, metainfos, tr, order, city):
        metainfo = utils.MetaInfo()

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
                    if col == 'city':
                        metainfo.set_city(txt)
                    
                    elif col == 'topic':
                        metainfo.set_topic(txt)
                    
                    elif col == 'department':
                        metainfo.set_department(txt)
                    
                    elif col == 'bundleno':
                        metainfo.set_bundleno(txt)
                    
                    elif col == 'year':
                        metainfo.set_year(txt)
                    
                    elif col == 'description':
                        metainfo.set_description(txt)
                    
                    elif col == 'file':
                        metainfo.set_file(txt)
                    
                    elif col == 'office':
                        metainfo.set_office(txt)
            i += 1

        if 'downloadurl' in metainfo:
            metainfos.append(metainfo)



    def parse_search_results(self, webpage, city, curr_page):
        metainfos = []
        has_nextpage = False
        results_per_page = None

        d = utils.parse_webpage(webpage, self.parser)
        if not d:
            self.logger.warning('Unable to parse search result page for %s', city)
            return metainfos, has_nextpage, results_per_page

        table = d.find('table', {'id': 'dataTable'})
        if table is None:
            self.logger.warning('Could not find the result table for %s', city)
            return metainfos, has_nextpage, results_per_page

        thead = table.find('thead')
        order = self.get_column_order(thead)
        tbody = table.find('tbody')
        for tr in tbody.find_all('tr'):
            self.process_result_row(metainfos, tr, order, city)


        div = d.find('div', {'class': 'dataTables_paginate'})
        if div is None:
            self.logger.warning('Could not find pagination div node for %s', city)
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
            self.logger.warning('Could not find page size node for %s', city)
            return metainfos, has_nextpage, results_per_page

        results_per_page = utils.get_selected_option(select)
        return metainfos, has_nextpage, results_per_page

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
        if search_doc_data is None:
            self.logger.warning('Unable to search for doc')
            return None

        download_query_params, download_postdata = self.get_download_postdata(search_doc_data, config, login_data)
        download_url = urllib.parse.urljoin(redirect_url, '../servlet/getdocstream')
        download_url += '?'
        download_url += urllib.parse.urlencode(download_query_params)

        return BaseGazette.pull_gazette(self, download_url, postdata = download_postdata, \
                                        cookiefile = cookiejar, referer = redirect_url_base, \
                                        encodepost = encodepost, headers = headers)


    def download_metainfo(self, relpath, metainfo): 
        metainfo = copy.deepcopy(metainfo)
        docview_url = metainfo.pop('downloadurl')
        postdata    = metainfo.pop('downloadpostdata')

        postdata_dict = dict(postdata)
        
        docid = postdata_dict['DC.DocumentID']
        relurl = os.path.join(relpath, docid)
        if self.save_gazette(relurl, docview_url, metainfo, \
                             postdata = postdata, validurl = False):
            return relurl

        return None


    def download_metainfo_wrapped(self, relpath, metainfo): 
        while True:
            try:
                return self.download_metainfo(relpath, metainfo)
            except DelayedRetryException:
                time.sleep(300)


    def download_nextpage(self, post_url, search_url, postdata, pagenum, results_per_page, cookiejar):
        newpost = []
        newpost.extend(postdata)
        newpost.append(('min', str(pagenum + 1)))
        newpost.append(('max', results_per_page))

        response = self.download_url(post_url, loadcookies = cookiejar, savecookies = cookiejar, \
                                     postdata = newpost, referer = search_url)

        return response


    def download_city(self, dls, city, event):
        cookiejar  = CookieJar()

        response = self.download_url(self.baseurl, savecookies = cookiejar)
        if response is None or response.webpage is None:
            self.logger.warning('Unable to get page %s', self.baseurl)
            return

        postdata = self.get_form_data(response.webpage, city)

        relpath = os.path.join(self.name, city.lower().replace(' ', '_'))

        search_url = urllib.parse.urljoin(self.baseurl, '/RSAD/Search')
        response = self.download_url(search_url, loadcookies = cookiejar, savecookies = cookiejar, postdata = postdata)

        pagenum = 1
        while response is not None and response.webpage is not None:
            metainfos, has_nextpage, results_per_page  = self.parse_search_results(response.webpage, city, pagenum)

            for metainfo in metainfos:
                relurl = self.download_metainfo_wrapped(relpath, metainfo)
                if relurl:
                    dls.append(relurl)


            if not has_nextpage:
                break

            response = self.download_nextpage(search_url, search_url, postdata, \
                                              pagenum, results_per_page, cookiejar)

            pagenum += 1


    def sync(self, fromdate, todate, event):
        dls = []

        city_list = self.get_city_list()

        for city, cval in city_list:
            self.download_city(dls, city, event)
            if event.is_set():
                self.logger.warning('Exiting prematurely as timer event is set')
                break


        return dls
 