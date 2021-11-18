import lxml.etree as ET
import sys
import logging
import os
import re

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
    
    def get_header(self, metadata):
        title       = metadata.get_value('title')
        locality    = metadata.get_value('locality')
        regyear     = metadata.get_value('regyear')
        regnum      = metadata.get_value('regnum')
        publishdate = metadata.get_value('publishdate')
        passedby    = metadata.get_value('passedby')

        frbr_uri = '/akn/us-%s/act/regulations/%s/%s' % (locality, regyear, regnum)

        frbr_work = '''
          <FRBRthis value="%s/!main" />
          <FRBRuri value="%s"/>
          <FRBRalias value="%s" name="title"/>
          <FRBRdate date="%s" name="Generation"/>
          <FRBRauthor href="#council"/>
          <FRBRcountry value="us-%s"/>
          <FRBRsubtype value="regulations"/>
          <FRBRnumber value="%s"/>
        ''' % (frbr_uri, frbr_uri, title, regyear, locality, regnum)

        frbr_expr = '''
          <FRBRthis value="%s/!main"/>
          <FRBRuri value="%s/en@%s"/>
          <FRBRdate date="%s" name="Generation"/>
          <FRBRauthor href="%s"/>
          <FRBRlanguage language="en"/>
        ''' % (frbr_uri, frbr_uri, publishdate, publishdate, passedby)

        frbr_manifest = '''
          <FRBRthis value="%s/!main"/>
          <FRBRuri value="%s/en@%s"/>
          <FRBRdate date="%s" name="Generation"/>
          <FRBRauthor href="#iklaws"/>
        ''' % (frbr_uri, frbr_uri, publishdate, publishdate)

        header = '''
    <akomaNtoso xmlns="http://docs.oasis-open.org/legaldocml/ns/akn/3.0">

  <act contains="originalVersion" name="act">
    <meta>
      <identification source="#iklaws">
        <FRBRWork>
        %s
        </FRBRWork>
        <FRBRExpression>
        %s
        </FRBRExpression>
        <FRBRManifestation>
        %s
        </FRBRManifestation>
      </identification>
      <publication number="" name="" showAs="" date="%s"/>
    </meta>''' % (frbr_work, frbr_expr, frbr_manifest, publishdate)

        return header


        return metadata


    def process_casemaker(self, xml_file, regulations):
        regs      = []
        file_info = FileInfo()
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
                num = regulation.num
                if num in regulations:
                    regulations[num].merge(regulation)
                else:
                    regulations[num] = regulation


    def process_regulation(self, file_info, node):
        body_akn    = create_node('body')
        preface_akn = create_node('preface')
        regulation  = Regulation()

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
                    regulation.name = child.text
                    pnode = create_node('p', preface_akn, {'class': 'title'})
                    title = create_node('shortTitle', pnode)
                    title.text = child.text
                elif child.tag == 'content':
                    self.process_preface(preface_akn, child)
                else:
                    pass

        return regulation

    def process_preface(self, preface_akn, node):
        for child in node:
            if ET.iselement(child):
                if child.tag == 'codetext':
                    self.process_preface_codetext(preface_akn, child)

    def process_preface_codetext(self, preface_akn, node):
        for child in node:
            if ET.iselement(child):
                if child.tag == 'para':
                    self.process_para( preface_akn, child)

    def process_para(self, parent_akn, node):
        pnode = create_node('p', parent_akn)
        pnode.text = node.text

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
                elif child.tag == 'subsect':
                    subsection_eid = '%s__subsec_%d' % (eId, subsection)
                    subsection += 1
                    self.process_subsection(section_akn, child, eId)
                    
        
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
                   if regulation.num == None:
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

class FileInfo:
    def __init__(self):
        self.root_name = None
        self.dept_name = None
        self.org_name  = None

    def  __repr__(self):
        return 'root: %s, dept: %s, org: %s' % (self.root_name, self.dept_name, self.org_name)

class Regulation:
    def __init__(self):
        self.root = None
        self.dept = None
        self.name = None
        self.statcd  = None
        self.num     = None
        self.chapnum = 1
        self.secnum  = 1
        self.partnum = 1
        self.publish_date = None
        self.body_akn = None

    def merge(self, other):
        pass

    def set_num(self, text):
        reobj = re.search('\d+', text)
        if reobj:
            self.num = text[reobj.start():reobj.end()]

    def write_akn_xml(self, outfile):
        akn_root = create_node('akomaNtoso', attribs = {'xmlns':'http://docs.oasis-open.org/legaldocml/ns/akn/3.0'})
        act_node = create_node('act', akn_root, attribs = {'contains': "originalVersion", 'name': 'act'})
        meta_node = create_node('meta', act_node)

        if self.preface_akn is not None:
           act_node.append(self.preface_akn)

        if self.body_akn is not None:
           act_node.append(self.body_akn)
        
        et = ET.ElementTree(akn_root)
        et.write(outfile, pretty_print=True, encoding='utf-8', \
                 xml_declaration=True)

if __name__ == '__main__':
    indir  = sys.argv[1]
    outdir = sys.argv[2]

    akn30 = Akn30()
    regulations = {}

    for filename in os.listdir(indir):
        if filename != 'mi-2021-admin-civilrights.xml':
            continue

        filepath = os.path.join(indir, filename)
        akn30.process_casemaker(filepath, regulations)

    for num, regulation in regulations.items():
        if num == None:
            continue

        filepath = os.path.join(outdir, '%s.xml' % num)
        regulation.write_akn_xml(filepath)
    
