import lxml.etree as ET
import sys
import logging
import os
import re
import datetime
import calendar

from egazette.us.states import states

def month_to_num(month):
    count = 0
    month = month.lower()
    for mth in calendar.month_name:
        if mth.lower() == month:
            return count
        count += 1
    return None

class Metadata:
    def __init__(self):
        self.d = {}

    def get_value(self, k):
        if k in self.d:
            return self.d[k]
        return ''

    def set_value(self, k, v):
        self.d[k] = v

def create_node(tagname, parent = None, attribs = None):
    node = ET.Element(tagname)

    if parent != None:
        parent.append(node)

    if attribs:
        for k, v in attribs.items():
            node.attrib[k] = v

    return node

class Akn30:
    def __init__(self):
        self.localities = {'MI': 'michigan'}
        self.logger = logging.getLogger('akn30')
    

    def process_casemaker(self, xml_file, regulations):
        regs      = []
        file_info = FileInfo('us')
        element_tree = ET.parse(xml_file)

        codeheader = element_tree.getroot()
        file_info.statecd  = codeheader.get('statecd')

        root_node = codeheader.find("code[@type='Root']")
        if root_node == None:
            self.logger.warning('Unable to find root node in %s', xml_file)
            return

        file_info.root_name = root_node.find('name').text
        dept_node = root_node.find("code[@type='Department']")
        if dept_node == None:
            self.logger.warning('Unable to find dept node in %s', xml_file)
            return

        file_info.dept_name = dept_node.find('name').text

        org_node = dept_node.find("code[@type='Undesignated']")
        if org_node == None:
            self.logger.warning('Unable to find org node in %s', xml_file)
            return

        file_info.org_name = org_node.find('name').text

        for child_node in org_node:
            if ET.iselement(child_node) and child_node.tag == 'code':
                regulation = self.process_regulation(file_info, child_node)
                num = regulation.get_num()
                if num in regulations:
                    regulations[num] = self.merge(regulations[num], regulation)
                else:
                    regulations[num] = regulation
            else:       
                self.logger.warning ('Ignored node in file %s', child_node)

    def merge(self, reg1, reg2):
        num1 = reg1.metadata.get_value('subnum')
        num2 = reg2.metadata.get_value('subnum')

        self.logger.warning('Merging %d %d', num1, num2)
        if num1 < num2:
            reg1.merge(reg2)
            return reg1
        else:
            reg2.merge(reg1)
            return reg2

    def process_regulation(self, file_info, node):
        body_akn    = create_node('body')
        preface_akn = create_node('preface')
        regulation  = Regulation(file_info.country, file_info.statecd, \
                                 file_info.org_name)

        regulation.body_akn    = body_akn
        regulation.preface_akn = preface_akn

        for child in node:
            if ET.iselement(child):
                if child.tag == 'version':
                    continue
                elif child.tag == 'code':
                    codetype =  child.get('type') 
                    if codetype == 'Section':
                        self.process_section(body_akn, child, regulation)
                    elif codetype == 'Chapter':    
                        self.process_chapter(body_akn, child, regulation)
                    elif codetype == 'Part':    
                        self.process_part(body_akn, child, regulation)
                elif child.tag == 'name':
                    regulation.set_title(child.text)
                    pnode = create_node('p', preface_akn, {'class': 'title'})
                    title = create_node('shortTitle', pnode)
                    title.text = child.text
                elif child.tag == 'content':
                    self.process_preface(preface_akn, child, regulation)
                else:    
                    self.logger.warning ('Ignored element in regulation %s', child.tag)
            else:       
                self.logger.warning ('Ignored node in regulation %s', child)

        return regulation

    def process_preface(self, preface_akn, node, regulation):
        for child in node:
            if ET.iselement(child):
                if child.tag == 'codetext':
                    self.process_preface_codetext(preface_akn, child)
                elif child.tag == 'currency':
                    regulation.set_publish_date(child.text)
                elif child.tag == 'notes':
                    self.process_notes(preface_akn, child)
                else:    
                    self.logger.warning ('Ignored element in preface %s', child.tag)
            else:       
                self.logger.warning ('Ignored node in preface %s', child)

    def process_preface_codetext(self, preface_akn, node):
        for child in node:
            if ET.iselement(child):
                if child.tag == 'para':
                    self.process_para( preface_akn, child)
                else:    
                    self.logger.warning ('Ignored element in preface codetext %s', child.tag)
            else:       
                self.logger.warning ('Ignored node in preface codetext %s', child)

    def process_para(self, parent_akn, node):
        pnode = create_node('p', parent_akn)

        if node.text:
            pnode.text = node.text
        else:
            pnode.text = ''

        for  child in node:
            if ET.iselement(child):
                if child.tag == 'bold':
                    bnode = create_node('b', pnode)
                    bnode.text = child.text
                    if child.tail:
                       bnode.tail = child.tail
                elif child.tag == 'italic':
                    inode = create_node('i', pnode)
                    inode.text = child.text
                    if child.tail:
                       inode.tail = child.tail
                else:
                    text = ET.tostring(child, method="text", encoding = "unicode")
                    if text:
                       pnode.text += text
            else:       
                self.logger.warning ('Ignored node in para %s', child)

    def process_chapter(self, body_akn, node, regulation):
        chap_akn = create_node('chapter', body_akn, \
                               {'eId': 'chap_%d' % regulation.chapnum})
        regulation.chapnum += 1

        for child in node:
            if ET.iselement(child):
                if child.tag == 'code' and child.get('type') == 'Section':
                    self.process_section(chap_akn, child, regulation)
                elif child.tag == 'number':
                    self.process_number(chap_akn, child)
                elif child.tag == 'name':
                   self.process_heading(chap_akn, child)
                else:    
                   self.logger.warning ('Ignored element in chapter %s', child.tag)
            else:       
                self.logger.warning ('Ignored node in chapter %s', child)

    def process_part(self, body_akn, node, regulation):
        part_akn = create_node('part', body_akn, \
                               {'eId': 'part_%d' % regulation.partnum})
        regulation.partnum += 1

        for child in node:
            if ET.iselement(child):
                if child.tag == 'code' and child.get('type') == 'Section':
                    self.process_section(part_akn, child, regulation)
                elif child.tag == 'number':
                    self.process_number(part_akn, child)
                elif child.tag == 'name':
                    self.process_heading(part_akn, child)
                else:    
                    self.logger.warning ('Ignored element in part %s', child.tag)
            else:       
                self.logger.warning ('Ignored node in part %s', child)

    def add_comment_node(self, parent):
        comment_node = create_node('remark', parent, {'status': 'editorial'})
        return comment_node

    def process_notes(self, parent_akn, node):
        comment_node = self.add_comment_node(parent_akn)

        for child in node:
            if ET.iselement(child):
                if child.tag == 'notes-citeas':
                    self.process_citeas_notes(comment_node, child)
                elif child.tag == 'notes-history':
                    self.process_notes_history(comment_node, child)
                elif child.tag == 'notes-maint':
                    self.process_notes_maint(comment_node, child)
                elif child.tag == 'notes-std':    
                    self.process_notes_std(comment_node, child)
                else:    
                    self.logger.warning ('Ignored element in notes %s', child.tag)
            else:       
                self.logger.warning ('Ignored node in notes %s', child)

    def process_notes_history(self, comment_node, node):
        pass

    def process_notes_maint(self, comment_node, node):
        for child in node:
            if ET.iselement(child) and child.tag == 'note':
                para_node = create_node('p', comment_node)
                text = ET.tostring(child, method = 'text', encoding = 'unicode')
                para_node.text = text
            else:       
                self.logger.warning ('Ignored node in notes-maint %s', child)

    def process_citeas_notes(self, comment_node, node):
        text = ET.tostring(node, method = 'text', encoding = 'unicode')
        citenode = create_node('neautralCitation', comment_node) 
        citenode.text = text

    def process_notes_std(self, comment_node, node):
        for child in node:
            if ET.iselement(child):
                if child.tag == 'note':
                    self.process_note(comment_node, child)
                else:    
                    self.logger.warning ('Ignored element in notes-std %s', child.tag)
            else:       
                self.logger.warning ('Ignored node in notes-std %s', child)
                 
    def process_note(self, comment_node, node):
        for child in node:
            if ET.iselement(child):
               if child.tag == 'para':
                   self.process_para(comment_node, child) 
               else:    
                   self.logger.warning ('Ignored element in note %s', child.tag)
            else:       
                 self.logger.warning ('Ignored node in note %s', child)

    def process_number(self, parent_akn, node):
        number_node = create_node('num', parent_akn)
        number_node.text = node.text

    def process_heading(self, parent_akn, node):
        heading_node = create_node('heading', parent_akn)
        heading_node.text = node.text

    def process_content(self, section_akn, node, eId, section_eid):
        hcontent_akn = create_node('hcontainer', section_akn, {'eId': eId})
        content_akn  = create_node('content', hcontent_akn)
        subsection   = 1

        for child in node:
            if ET.iselement(child):
                if child.tag == 'currency':
                    pass
                elif child.tag == 'codetext':    
                    self.process_codetext(content_akn, child, section_akn, section_eid)
                elif child.tag == 'notes':
                    self.process_notes(content_akn, child)
                elif child.tag == 'subsect':
                    subsection_eid = '%s__subsec_%d' % (eId, subsection)
                    subsection += 1
                    self.process_subsection(section_akn, child, eId)
                else:    
                    self.logger.warning ('Ignored element in content %s', child.tag)
            else:       
                self.logger.warning ('Ignored node in content %s', child)
                    
        
    def process_codetext(self, parent_akn, node, section_akn, section_eid):
        subsection   = 1
        for child in node:
            if ET.iselement(child):
                if child.tag == 'para':
                    self.process_para(parent_akn, child)
                elif child.tag == 'subsect':
                    subsection_eid = '%s__subsec_%d' % (section_eid, subsection)
                    subsection += 1
                    self.process_subsection(section_akn, child, subsection_eid)
                else:    
                    self.logger.warning ('Ignored element in codetext %s', child.tag)
            else:       
                self.logger.warning ('Ignored node in codetext %s', child)
                    

    def process_section(self, parent_akn, node, regulation):
        eId = 'sec_%d' % regulation.secnum
        regulation.secnum += 1
        content_num       = 1
        subsection        = 1
        section_akn = create_node('section', parent_akn, \
                                      {'eId': eId})

        for child in node:
            if ET.iselement(child):
                if child.tag == 'subsect':
                   subsection_eid = '%s__subsec_%d' % (eId, subsection)
                   subsection += 1
                   self.process_subsection(section_akn, child, subsection_eid)
                elif child.tag == 'number':
                   self.process_number(section_akn, child)
                   regulation.set_num(child.text)
                elif child.tag == 'name':
                   self.process_heading(section_akn, child)
                elif child.tag == 'content':
                   content_eid = '%s__hcontainer_%d' % (eId, content_num)
                   self.process_content(section_akn, child, content_eid, eId)
                   content_num += 1
                elif child.tag == 'version':
                   # no idea what to do about the version tag
                   pass
                elif child.tag == 'notes':
                    self.process_notes(section_akn, child)
                else:    
                    self.logger.warning ('Ignored element in section %s', child.tag)
            else:       
                self.logger.warning ('Ignored node in section %s', child)


    def process_subsection(self, section_akn, node, eId):
        subsection_akn = create_node('subsection', section_akn, {'eId': eId})
        content_akn    = None
        subsection     = 1
        for child in node:
            if ET.iselement(child):
                if child.tag == 'designator':
                    self.process_number(subsection_akn, child)
                    content_akn = create_node('content', subsection_akn)
                elif child.tag == 'subsect':
                    subsection_eid = '%s__subsec_%d' % (eId, subsection)
                    subsection += 1
                    self.process_subsection(subsection_akn, child, subsection_eid)
                elif child.text and child.text.strip():
                    para_node = create_node('p', content_akn)
                    para_node.text = child.text

                if child.tail and child.tail.strip():
                   para_node = create_node('p', content_akn)
                   para_node.text = child.tail
            else:       
                self.logger.warning ('Ignored node in subsection %s', child)

class FileInfo:
    def __init__(self, country):
        self.country   = country
        self.root_name = None
        self.dept_name = None
        self.org_name  = None

    def  __repr__(self):
        return 'root: %s, dept: %s, org: %s' % (self.root_name, self.dept_name, self.org_name)

class Regulation:
    def __init__(self, country, statecd, author):
        self.root = None
        self.dept = None
        self.name = None
        self.locality  = states.locality[statecd]
        self.chapnum = 1
        self.secnum  = 1
        self.partnum = 1
        self.publish_date = None
        self.body_akn = None

        self.metadata = Metadata()
        self.metadata.set_value('country', country)
        self.metadata.set_value('locality', self.locality)
        self.metadata.set_value('regyear', states.start_year[statecd])
        self.metadata.set_value('author', author)

    def __repr__(self):
        return '%s' % self.metadata.d

    def get_frbr_uri(self):
        locality    = self.metadata.get_value('locality')
        country     = self.metadata.get_value('country')
        regyear     = self.metadata.get_value('regyear')
        regnum      = self.metadata.get_value('regnum')
        frbr_uri = '/akn/%s-%s/act/regulations/%s/%s' % (country, locality, regyear, regnum)
        return frbr_uri

    def add_header(self, meta_node):
        title       = self.metadata.get_value('title')
        country     = self.metadata.get_value('country')
        locality    = self.metadata.get_value('locality')
        regyear     = self.metadata.get_value('regyear')
        regnum      = self.metadata.get_value('regnum')
        publishdate = self.metadata.get_value('publishdate')
        author      = self.metadata.get_value('author')
        lang        = 'eng'
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

        expr_uri = '%s/%s@%s' % (frbr_uri, lang, publishdate)
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
        create_node('TLCOrganization', refnode, {'eId': 'council', 'showAs': author})

    def update_chap_num(self, node):
        node.set('eId', 'chap_%d' % self.chapnum)
        self.chapnum += 1
        for child in node:
            if ET.iselement(child):
                if child.tag == 'section':
                    self.update_section_num(child)
                elif child.tag == 'part':
                    self.update_part_num(child)
        
    def update_part_num(self, node):
        node.set('eId', 'part_%d' % self.partnum)
        self.partnum += 1
        for child in node:
            if ET.iselement(child) and child.tag == 'section':
                self.update_section_num(child)

    def update_section_num(self, node):
        eId = 'sec_%d' % self.secnum
        node.set('eId', eId) 
        self.secnum += 1

        subsection  = 1
        content_num = 1
        for child in node:
            if ET.iselement(child):
                if child.tag == 'subsection':
                    subsection_eid = '%s__subsec_%d' % (eId, subsection)
                    child.set('eId', subsection_eid)
                    subsection += 1
                elif child.tag == 'hcontainer':
                    content_eid = '%s__hcontainer_%d' % (eId, content_num)
                    child.set('eId', content_eid)
                    content_num += 1

    def merge(self, other):
        if len(other.preface_akn) > 0:
            self.body_akn.append(other.preface_akn)

        for child in other.body_akn:
            if ET.iselement(child):
                if child.tag == 'chapter':
                    self.update_chap_num(child)
                elif child.tag == 'part':    
                    self.update_part_num(child)
                elif child.tag == 'section':    
                    self.update_section_num(child)
                else:
                    self.logger.warn('Merge: Unknown tag %s', child.tag)

            self.body_akn.append(child)

    def get_num(self):
        return self.metadata.get_value('regnum')

    def set_num(self, text):
        if  self.metadata.get_value('regnum'):
            return

        nums = re.findall('\d+', text)
        if nums:
            self.metadata.set_value('regnum',  nums[0])
            if len(nums) > 1:
                 self.metadata.set_value('subnum', int(nums[1]))

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
           act_node.append(self.body_akn)
        
        et = ET.ElementTree(akn_root)
        et.write(outfile, pretty_print=True, encoding='utf-8', \
                 xml_declaration=xml_decl)

if __name__ == '__main__':
    indir  = sys.argv[1]
    outdir = sys.argv[2]

    akn30 = Akn30()
    regulations = {}

    for filename in os.listdir(indir):
        filepath = os.path.join(indir, filename)
        akn30.process_casemaker(filepath, regulations)

    for num, regulation in regulations.items():
        if num == None:
            continue

        filepath = os.path.join(outdir, '%s.xml' % num)
        regulation.write_akn_xml(filepath)
    
