import calendar
import datetime
import re
import logging
import lxml.etree as ET

from . import states
from .resolver import RefResolver

def month_to_num(month):
    count = 0
    month = month.lower()
    for mth in calendar.month_name:
        if mth.lower() == month:
            return count
        count += 1
    return None

def create_node(tagname, parent = None, attribs = None):
    node = ET.Element(tagname)

    if parent != None:
        parent.append(node)

    if attribs:
        for k, v in attribs.items():
            node.attrib[k] = v

    return node


class Metadata:
    def __init__(self):
        self.d = {}

    def get_value(self, k):
        if k in self.d:
            return self.d[k]
        return ''

    def set_value(self, k, v):
        self.d[k] = v


class Regulation:
    def __init__(self, country, statecd, author):
        self.root = None
        self.dept = None
        self.name = None
        self.statecd = statecd
        self.locality= states.locality[statecd]
        self.chapnum = 1
        self.secnum  = 1
        self.partnum = 1
        self.subpart = 1
        self.divnum  = 1
        self.contentnum = 1
        self.articlenum = 1
        self.publish_date = None
        self.body_akn = None
        self.logger = logging.getLogger('regulation')

        self.metadata = Metadata()
        self.metadata.set_value('country', country)
        self.metadata.set_value('locality', self.locality)
        self.metadata.set_value('regyear', states.start_year[statecd])
        self.metadata.set_value('author', author)
        self.metadata.set_value('language', 'eng')

    def __repr__(self):
        return '%s' % self.metadata.d

    def get_doctype(self, locality):
        if locality == 'california':
            doctype = 'title'
        else:
            doctype = 'regulations'
        return doctype    

    def get_frbr_uri(self):
        locality    = self.metadata.get_value('locality')
        country     = self.metadata.get_value('country')
        regyear     = self.metadata.get_value('regyear')
        regnum      = self.metadata.get_value('regnum')
        doctype     = self.get_doctype(locality)
        frbr_uri = '/akn/%s-%s/act/%s/%s/%s' % (country, locality, doctype, regyear, regnum)
        return frbr_uri

    def get_expr_uri(self):
        frbr_uri    = self.get_frbr_uri()
        lang        = self.metadata.get_value('language')
        publishdate = self.metadata.get_value('publishdate')
        if isinstance(publishdate, str):
            print (frbr_uri)
        publishdate = publishdate.strftime('%Y-%m-%d')
        return '%s/%s@%s' % (frbr_uri, lang, publishdate)

    def add_header(self, meta_node):
        title       = self.metadata.get_value('title')
        country     = self.metadata.get_value('country')
        locality    = self.metadata.get_value('locality')
        regyear     = self.metadata.get_value('regyear')
        regnum      = self.metadata.get_value('regnum')
        publishdate = self.metadata.get_value('publishdate')
        author      = self.metadata.get_value('author')
        lang        = self.metadata.get_value('language')
        publishdate = publishdate.strftime('%Y-%m-%d')
        frbr_uri    = self.get_frbr_uri()

        
        idnode = create_node('identification', meta_node, \
                             {'source': '#casemaker'})
        work_node = create_node('FRBRWork', idnode)
        expr_node = create_node('FRBRExpression', idnode)
        manifest_node = create_node('FRBRManifestation', idnode)

        create_node('FRBRthis',  work_node, {'value': '%s/!main' % frbr_uri})
        create_node('FRBRuri',   work_node, {'value': frbr_uri})
        create_node('FRBRalias', work_node, {'value': title, 'name': 'title'})
        create_node('FRBRdate',  work_node, {'date': regyear, 'name': 'Generation'})
        create_node('FRBRauthor',  work_node, {'href': '#council'})
        create_node('FRBRcountry', work_node, {'value': '%s-%s' % (country, locality)})
        create_node('FRBRsubtype', work_node, {'value': 'regulations'})
        create_node('FRBRnumber',  work_node, {'value': regnum})

        expr_uri = self.get_expr_uri()
        create_node('FRBRthis', expr_node, {'value': '%s/!main' % expr_uri})
        create_node('FRBRuri',  expr_node, {'value': expr_uri})
        create_node('FRBRdate', expr_node, {'date': publishdate, 'name': 'Generation'})
        create_node('FRBRauthor', expr_node, {'href': '#council'})
        create_node('FRBRlanguage', expr_node, {'language': lang})


        create_node('FRBRthis', manifest_node, {'value': '%s/!main' % expr_uri})
        create_node('FRBRuri',  manifest_node, {'value': expr_uri})
        create_node('FRBRdate', manifest_node, {'date': publishdate, 'name': 'Generation'})
        create_node('FRBRauthor', manifest_node, {'href': '#council'})

        create_node('publication', meta_node, \
                 {'number': '', 'name': '', 'showAs': '', 'date': publishdate})
        refnode = create_node('references', meta_node, {'source': '#this'})

        refdict = {'eId': 'council'}
        if author:
            refdict['showAs'] = author
        create_node('TLCOrganization', refnode, refdict)

    def update_chap_num(self, node):
        node.set('eId', 'chap_%d' % self.chapnum)
        self.chapnum += 1
        for child in node:
            if ET.iselement(child):
                if child.tag == 'section':
                    self.update_section_num(child)
                elif child.tag == 'part':
                    self.update_part_num(child)
                elif child.tag == 'article':
                    self.update_article_num(child)
                elif child.tag == 'hcontainer':
                    self.update_hcontainer_num(child)
                elif child.tag == 'subchapter':
                    self.update_subchapter_num(child)
                elif child.tag in ['num', 'heading']:
                    pass
                elif child.get('eId'):
                    self.logger.warning('Unable to update num in chapter %s', child.tag)
        
    def update_part_num(self, node):
        node.set('eId', 'part_%d' % self.partnum)
        self.partnum += 1
        for child in node:
            if ET.iselement(child) and child.tag == 'section':
                self.update_section_num(child)
            elif ET.iselement(child) and child.tag == 'hcontainer':
                self.update_hcontainer_num(child)
            elif child.tag in ['num', 'heading']:
                pass
            elif ET.iselement(child) and child.tag == 'subpart':
                self.update_subpart_num(child)
            elif child.get('eId'):
                self.logger.warning('Unable to update num in part %s', child.tag)

    def update_subchapter_num(self, node):
        for child in node:
            if ET.iselement(child):
                if child.tag == 'section':
                    self.update_section_num(child)
                elif child.tag == 'part':
                    self.update_part_num(child)
                elif child.tag == 'content':
                    self.update_content_num(child)
                elif child.tag == 'hcontainer':
                    self.update_hcontainer_num(child)
                elif child.tag == 'article':
                    self.update_article_num(child)
                elif child.tag in ['num', 'heading']:
                    pass
                elif child.get('eId'):
                    self.logger.warning('Unable to update num in subsection %s', child.tag)

    def update_article_num(self, node):
        eId = 'article_%d' % self.articlenum
        self.articlenum += 1
        node.set('eId', eId) 

        for child in node:
            if ET.iselement(child):
                if child.tag == 'section':
                    self.update_section_num(child)
                elif child.tag == 'part':
                    self.update_part_num(child)
                elif child.tag == 'hcontainer':
                    self.update_hcontainer_num(child)
                elif child.tag in ['num', 'heading']:
                    pass
                elif child.get('eId'):
                    self.logger.warning('Unable to update num in article %s %s', child.tag, child.get('eId'))

    def update_section_num(self, node):
        eId = 'sec_%d' % self.secnum
        node.set('eId', eId) 
        self.secnum += 1

        subsection  = 1
        for child in node:
            if ET.iselement(child):
                if child.tag == 'subsection':
                    subsection_eid = '%s__subsec_%d' % (eId, subsection)
                    child.set('eId', subsection_eid)
                    subsection += 1
                elif child.tag == 'hcontainer':
                    self.update_hcontainer_num(child)
                elif child.tag in ['num', 'heading']:
                    pass
                elif child.get('eId'):
                    self.logger.warning('Unable to update num in section %s', child.tag)

    def update_division_num(self, node):
        eId = 'division_%d' % self.divnum
        node.set('eId', eId) 
        self.divnum += 1

        subdivision  = 1
        subchapter   = 1
        for child in node:
            if ET.iselement(child):
                if child.tag == 'subdivision':
                    subdivision_eid = '%s__subdivision_%d' % (eId, subdivision)
                    child.set('eId', subdivision_eid)
                    subdivision  += 1
                elif child.tag == 'chapter':
                     self.update_chap_num(child)
                elif child.tag == 'subchapter':
                    child.set('eId', '%s_subchap_%d' % (eId, subchapter))
                    subchapter += 1
                elif child.tag == 'section':
                    self.update_section_num(child)
                elif child.tag == 'part':
                    self.update_part_num(child)
                elif child.tag == 'article':
                    self.update_article_num(child)
                elif child.tag == 'hcontainer':
                    self.update_hcontainer_num(child)
                elif child.tag in ['num', 'heading']:
                    pass
                elif child.get('eId'):
                    self.logger.warning('Unable to update num in division for %s %s', child.tag, child.get('eId'))

    def update_content_num(self, node):
        eId = node.get('eId')
        if eId == None:
            eId = node.getparent().get('eId')

        subsection = 1
        for child in node:
            if ET.iselement(child):
                if child.tag == 'section':
                    self.update_section_num(child)
                elif child.tag == 'part':
                    self.update_part_num(child)
                elif child.tag == 'content':
                    self.update_content_num(child)
                elif child.tag == 'hcontainer':
                    self.update_hcontainer_num(child)
                elif child.tag == 'article':
                    self.update_article_num(child)
                elif child.tag == 'subsection' and eId:
                    subsection_eid = '%s__subsec_%d' % (eId, subsection)
                    subsection += 1
                    child.set('eId', subsection_eid)

                elif child.tag in ['num', 'heading', 'p', 'remark', 'neutralCitation']:
                    pass
                elif child.get('eId'):
                    self.logger.warning('Unable to update num in content %s', child.tag)


    def update_hcontainer_num(self, node):
        eId = 'hcontainer_%d' % self.contentnum
        node.set('eId', eId) 
        self.contentnum += 1
        for child in node:
            if ET.iselement(child):
                if child.tag == 'section':
                    self.update_section_num(child)
                elif child.tag == 'part':
                    self.update_part_num(child)
                elif child.tag == 'content':
                    self.update_content_num(child)
                elif child.tag == 'hcontainer':
                    self.update_hcontainer_num(child)
                elif child.tag in ['num', 'heading']:
                    pass
                elif child.get('eId'):
                    self.logger.warning('Unable to update num in hcontainer %s', child.tag)

    def update_subpart_num(self, node):
        eId = 'subpart_%d' % self.subpart
        node.set('eId', eId) 
        self.subpart += 1
        for child in node:
            if ET.iselement(child):
                if child.tag == 'section':
                    self.update_section_num(child)
                elif child.tag == 'article':
                    self.update_article_num(child)
                elif child.tag in ['num', 'heading']:
                    pass
                elif child.get('eId'):
                    self.logger.warn('Unable to update num in subpart %s', child.tag)
 

    def merge(self, other):
        if len(other.preface_akn) > 0:
            self.body_akn.append(other.preface_akn)

        refresolver = RefResolver()
        refresolver.add_sections(self.body_akn, None, None)

        duplicates = []
        for node in other.body_akn.iter('section'):
            dup = refresolver.is_duplicate(node)
            if dup:
                self.logger.warning('Duplicate found %s. Removing', dup)
                duplicates.append(node)
            
        for node in duplicates:
            node.getparent().remove(node)

        for child in other.body_akn:
            if ET.iselement(child):
                num = child.get('eId')

                if child.tag == 'chapter':
                    self.update_chap_num(child)
                elif child.tag == 'part':    
                    self.update_part_num(child)
                elif child.tag == 'section':    
                    self.update_section_num(child)
                elif child.tag == 'hcontainer':    
                    self.update_hcontainer_num(child)
                elif child.tag == 'subpart':    
                    self.update_subpart_num(child)
                elif child.tag == 'division':    
                    self.update_division_num(child)
                elif num == None:    
                    pass
                else:
                    self.logger.warning('Merge: Unknown tag for updating num %s', ET.tostring(child))
            self.body_akn.append(child)

    def get_num(self):
        return self.metadata.get_value('regnum')

    def set_num(self, text):
        if  self.metadata.get_value('regnum'):
            return

        nums = re.findall('[\w-]+', text)

        if nums:
            self.metadata.set_value('regnum',  nums[0].lower())
            if len(nums) > 1:
                self.metadata.set_value('subnum', int(nums[1]))

    def set_subnum(self, text):
        if (not self.metadata.get_value('regnum')) or \
                self.metadata.get_value('subnum'):
            return

        nums = re.findall('\d+', text)
        if nums:
            self.metadata.set_value('subnum', int(nums[0]))

    def get_title(self):
        return self.metadata.get_value('title')

    def set_title(self, title):
        self.metadata.set_value('title', title)

    def get_publish_date(self):
        return  self.metadata.get_value('publishdate')

    def get_locality(self):
        return  self.metadata.get_value('locality')

    def get_country(self):
        return  self.metadata.get_value('country')

    def get_regyear(self):
        return self.metadata.get_value('regyear')

    def get_regnum(self):
        return self.metadata.get_value('regnum')

    def set_publish_date(self, currency_text):
        if self.get_publish_date():
            return

        dateobj = self.extract_date(currency_text)
        if dateobj:
            self.metadata.set_value('publishdate', dateobj)


    def extract_date(self, text):
        monthre = 'january|february|march|april|may|june|july|august|september|october|november|december'
        reobj = re.search('(?P<day>\d+)(st|nd|rd|th)?\s+(?P<month>%s)[\s,]+(?P<year>\d+)' % monthre, text, flags=re.IGNORECASE)


        dateobj = None

        if not reobj:
            reobj = re.search('(?P<month>%s)\s+(?P<day>\d+)[\s,]+(?P<year>\d+)' % monthre, text, flags=re.IGNORECASE)

        if reobj:
            groups = reobj.groupdict()
            dateobj = datetime.date(int(groups['year']),  month_to_num(groups['month']), int(groups['day']))
        return dateobj

    def remove_version(self):
        for version in self.body_akn.iter('version'):
            version.getparent().remove(version)

    def write_akn_xml(self, outfile, xml_decl = True):
        akn_root = create_node('akomaNtoso', attribs = \
                  {'xmlns':'http://docs.oasis-open.org/legaldocml/ns/akn/3.0'})
        act_node = create_node('act', akn_root, attribs = \
                  {'contains': "originalVersion", 'name': 'act'})
        meta_node = create_node('meta', act_node)
        self.add_header(meta_node)

        if self.preface_akn is not None:
           act_node.append(self.preface_akn)

        if self.body_akn is not None:
           self.remove_version()
           act_node.append(self.body_akn)
        
        et = ET.ElementTree(akn_root)
        et.write(outfile, pretty_print=True, encoding='utf-8', \
                 xml_declaration=xml_decl)

