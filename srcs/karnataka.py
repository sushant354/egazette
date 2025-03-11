import re
import os
from io import BytesIO
import urllib.request, urllib.parse, urllib.error
import datetime

from ..utils import utils
from .basegazette import BaseGazette
from ..utils.metainfo import MetaInfo

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

        mainmeta = MetaInfo()
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

            metainfo = MetaInfo()
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
       

