import re
import os
from StringIO import StringIO
import urllib
import datetime

import utils
from basegazette import BaseGazette

class Karnataka(BaseGazette):
    def __init__(self, name, storage):
        BaseGazette.__init__(self, name, storage)

        self.baseurl    = 'http://www.gazette.kar.nic.in/%s/'
        self.hostname   = 'www.gazette.kar.nic.in'
        self.flip_date1 = datetime.date(2009, 03, 05)
        self.flip_date2 = datetime.date(2013, 03, 07)

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
        docurl  = urllib.basejoin(dateurl, mainhref)

        metainfo = utils.MetaInfo()
        metainfo.set_date(dateobj)
       
        response = self.download_url(docurl)
        if not response or not response.webpage or response.error:
            return dls

        relurl = os.path.join(relpath, 'main')
        updated = False
        if self.storage_manager.save_rawdoc(self.name, relurl, response.srvresponse, response.webpage):
            self.logger.info(u'Saved rawfile %s' % relurl)
            updated = True

        if self.storage_manager.save_metainfo(self.name, relurl, metainfo):
            updated = True
            self.logger.info(u'Saved metainfo %s' % relurl)

        if updated:    
            dls.append(relurl)

        page_type = self.get_file_extension(response.webpage)
        if page_type != 'pdf':
            self.logger.warn('Got a non-pdf page and we can\'t handle it for datte %s', dateobj)
            return dls

        hrefs = utils.extract_links_from_pdf(StringIO(response.webpage))
        for href in hrefs:
            reobj = re.search('(?P<num>Part-\w+)', href)
            if reobj:
                partnum = reobj.groupdict()['num']
            else:
                partnum = href
                 
            relurl = os.path.join(relpath, partnum)
            docurl = urllib.basejoin(dateurl, href) 

            metainfo = utils.MetaInfo()
            metainfo.set_date(dateobj)
            metainfo['partnum'] = partnum

            if self.save_gazette(relurl, docurl, metainfo):
                dls.append(relurl)

        return dls    
       

