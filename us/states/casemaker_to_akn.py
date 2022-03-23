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

class DTDResolver(ET.Resolver):
    def resolve(self, url, public_id, context):
        dirname = os.path.dirname(os.path.realpath(__file__))
        filename = os.path.join(dirname, 'HTMLLat2.ent')
        return self.resolve_filename(filename, context)

class RefResolver:
    def __init__(self):
        self.refids = {}
        self.logger = logging.getLogger('refresolver')

    def normalize_num(self, num):
        return ' '.join(num.split())

    def add_refid(self, num, uri, eid, version, regs_title):
        if regs_title:
            if regs_title not in self.refids:
                 self.refids[regs_title] = {}

            refids = self.refids[regs_title]
        else:
            refids = self.refids

        num = self.normalize_num(num)
        if num in refids:
            oldver = refids[num][2]
            if version <= oldver:
                self.logger.warning('Refid already exists %s %s for (%s, %s, %s)', num, refids[num], uri, eid, version)
                return
            else:
                self.logger.warning('Refid replacement of %s %s with (%s, %s, %s)', num, refids[num], uri, eid, version)
                
        refids[num] = (uri, eid, version)

    def resolve_num(self, title, num):
        num = self.normalize_num(num)

        if title:
            if title in self.refids:
                refids = self.refids[title]
            else:    
                return None, None, None
        else:
            refids = self.refids

        if num in refids:
            return refids[num]

        return None, None, None

    def add_regulation(self, regulation):
        uri = regulation.get_expr_uri()
        regs_title = None 
        if regulation.statecd == 'CA':
            num = regulation.get_num()
            if not num:
                self.logger.warning ('RefResolver: NO NUM %s', regulation)
                return

            regs_title = num
        self.add_sections(regulation.body_akn, uri, regs_title)

    def add_sections(self, akn, uri, regs_title):    
        for node in akn.iter('section'):
            numnode = node.find('num')
            if numnode == None:
                continue

            version = node.find('version')
            if version != None:
                version = int(version.text)

            num =  numnode.text
            self.add_refid(num, uri, node.get('eId'), version, regs_title)

    def is_duplicate(self, node):
        num = node.find('num').text

        uri, eId, version = self.resolve_num(None, num)
        if eId:
           newver = node.find('version')
           if newver != None: 
               newver = int(newver.text)

           return num
        return None   
        
    def resolve(self, regulation):
        reguri = regulation.get_expr_uri()
        for node in regulation.body_akn.iter('ref'):
            text = node.get('use')
            title = node.get('title')
            if not text:
                text = node.text

            if not text:
                self.logger.warning('Nothing to resolve here %s %s', ET.tostring(node), reguri)
                continue

            d  = self.resolve_num(title, text)
            uri, eId, version = d 
            if uri == None:
                self.logger.warning('Could not resolve %s %s', title, text)
                continue

            if uri == reguri:
                href = '#%s' % eId
            else:
                href = '%s#%s' % (uri, eId)

            node.attrib['href'] = href
            

class Akn30:
    def __init__(self, media_url):
        self.media_url  = media_url
        self.localities = {'MI': 'michigan'}
        self.logger     = logging.getLogger('akn30')
        self.statecd    = None
    

    def process_casemaker(self, xml_file, regulations):
        regs      = []

        file_info = FileInfo('us')
        parser = ET.XMLParser(load_dtd = True)
        parser.resolvers.add( DTDResolver())

        fhandle = open(xml_file, 'rb')
        element_tree = ET.parse(fhandle, parser = parser)

        codeheader = element_tree.getroot()
        file_info.statecd  = codeheader.get('statecd')
        self.statecd       = codeheader.get('statecd')

        root_node = codeheader.find("code[@type='Root']")
        if root_node == None:
            self.logger.warning('Unable to find root node in %s', xml_file)
            return

        file_info.root_name = root_node.find('name').text

        for child in root_node:
            if ET.iselement(child):
                if child.tag == 'code':
                    codetype = child.get('type')
                    if codetype == 'Title':
                        self.process_code(child, file_info, regulations)
                    else:
                        self.process_dept(child, file_info, regulations)

                elif child.tag == 'name':
                    file_info.dept_name = child.text
                else:
                    self.logger.warn('Ignord element in root %s', child.tag)
            else:       
                self.logger.warning ('Ignored node in root %s', child)
        fhandle.close()
   
    def process_dept(self, node, file_info, regulations):   
        for child in node:
            if ET.iselement(child):
                child_code = child.find('code')
                if child.tag == 'code' and child_code != None:
                    codetype = child_code.get('type')
                    if codetype == 'Undesignated':
                        self.process_org(child, file_info, regulations)
                    else:    
                        self.process_code(child, file_info, regulations)
                elif child.tag == 'name':
                    file_info.dept_name = child.text
                else:
                    self.logger.warning('Ignord element in dept %s', child.tag)
            else:       
                self.logger.warning ('Ignored node in dept %s', child)

    def process_code(self, node, file_info, regulations):
        regulation = self.process_regulation(file_info, node)
        num = regulation.get_num()
        if not num:
            self.logger.warning ('NO NUM %s', regulation)
            return

        if num in regulations:
            regulations[num] = self.merge(regulations[num], regulation)
        else:
            regulations[num] = regulation

        return regulations[num] 

    def process_org(self, node, file_info, regulations):
        regulation = None
        for child_node in node:
            if ET.iselement(child_node):
                if child_node.tag == 'code':
                    codetype = child_node.get('type')
                    if codetype == 'Undesignated':
                        regulation = self.process_code(child_node, file_info, regulations)
                    elif codetype == 'Part':    
                        self.process_part(regulation.body_akn, child_node, regulation)
                    else:
                        self.logger.warning('Unknown codetype in org %s', codetype)
            elif ET.iselement(child_node) and child_node.tag == 'name':
                file_info.org_name = child_node.text
            elif ET.iselement(child_node) and child_node.tag == 'version':
                pass 
            else:       
                self.logger.warning ('Ignored node in org %s', ET.tostring(child_node))

    def merge(self, reg1, reg2):
        num1 = reg1.metadata.get_value('subnum')
        num2 = reg2.metadata.get_value('subnum')

        self.logger.warning('Merging %d %d of %s', num1, num2, reg1.get_num())
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
                elif child.tag == 'number':
                    regulation.set_num(child.text)
                elif child.tag == 'code':
                    codetype =  child.get('type') 
                    if codetype == 'Section':
                        self.process_section(body_akn, child, regulation)
                    elif codetype == 'Division':    
                        self.process_division(body_akn, child, regulation)
                    elif codetype == 'Chapter':    
                        self.process_chapter(body_akn, child, regulation)
                    elif codetype == 'Part' or codetype == 'Subpart':    
                        self.process_part(body_akn, child, regulation)
                    elif codetype == 'Undesignated':
                        self.process_subcode(body_akn, child, regulation)
                    elif codetype == 'RegulationNo':
                        self.process_division(body_akn, child, regulation)
                    else:    
                        self.logger.warning ('Ignored codetype in regulation %s', codetype)
                elif child.tag == 'name':
                    regulation.set_title(child.text)
                    pnode = create_node('p', preface_akn, {'class': 'title'})
                    title = create_node('shortTitle', pnode)
                    title.text = child.text
                elif child.tag == 'content':
                    self.process_preface(preface_akn, child, regulation)
                else:    
                    self.logger.warning ('Ignored element in regulation %s', ET.tostring(child))
            else:       
                self.logger.warning ('Ignored node in regulation %s', child)

        return regulation

    def process_division(self, parent_akn, node, regulation):
        eId = 'division_%d' % regulation.divnum
        regulation.divnum += 1
        div_akn = create_node('division', parent_akn, {'eId': eId})

        subdiv  = 1
        subchap = 1
        content_num = 1
        for child in node:
            if ET.iselement(child):
                if child.tag == 'code' and child.get('type') == 'Chapter':
                    self.process_chapter(div_akn, child, regulation)
                elif child.tag == 'code' and child.get('type') == 'Section':
                    self.process_section(div_akn, child, regulation)
                elif child.tag == 'code' and child.get('type') == 'Article':
                    self.process_article(div_akn, child, regulation)
                elif child.tag == 'code' and child.get('type')=='Undesignated':
                    self.process_part(div_akn, child, regulation)
                elif child.tag == 'code' and child.get('type') == 'Part':
                    self.process_part(div_akn, child, regulation)
                elif child.tag == 'code' and child.get('type')=='Appendix':
                    self.process_appendix(div_akn, child, regulation)
                elif child.tag == 'code' and child.get('type') == 'Subdivision':
                    subdivision_eid = '%s_subdivision_%d' % (eId, subdiv)
                    subdiv += 1
                    self.process_subdivision(div_akn, child, regulation, subdivision_eid)
                elif child.tag == 'code' and child.get('type') == 'Subchapter':
                    subchap_eId = '%s_subchap_%d' % (eId, subchap)
                    subchap += 1
                    self.process_subchapter(div_akn, child, regulation, subchap_eId)
                elif child.tag == 'number':
                    self.process_number(div_akn, child)
                    regulation.set_subnum(child.text)
                elif child.tag == 'name':
                   self.process_heading(div_akn, child)
                elif child.tag == 'content':
                    content_eid = '%s__hcontainer_%d' % (eId, content_num)
                    content_num += 1
                    self.process_content(div_akn, child, content_eid, eId, regulation)
                elif child.tag == 'version':
                    pass
                else:    
                   self.logger.warning ('Ignored element in division %s', ET.tostring(child))
            else:       
                self.logger.warning ('Ignored node in division %s', child)

    def process_subdivision(self, parent_akn, node, regulation, eId):
        div_akn = create_node('subdivision', parent_akn, {'eId': eId})

        division = 1
        for child in node:
            if ET.iselement(child):
                if child.tag == 'code' and child.get('type') == 'Chapter':
                    self.process_chapter(div_akn, child, regulation)
                elif child.tag == 'code' and child.get('type') == 'Section':
                    self.process_section(div_akn, child, regulation)
                elif child.tag == 'code' and child.get('type') == 'Part':
                    self.process_part(div_akn, child, regulation)
                elif child.tag == 'code' and child.get('type') == 'Division':
                    div_eid = '%s_division_%d' % (eId, division)
                    division += 1
                    self.process_subdivision(parent_akn, child, regulation, div_eid)
                elif child.tag == 'number':
                    self.process_number(div_akn, child)
                elif child.tag == 'name':
                   self.process_heading(div_akn, child)
                else:    
                   self.logger.warning ('Ignored element in subdivision %s', ET.tostring(child))
            else:       
                self.logger.warning ('Ignored node in subdivision %s', child)


    def process_preface(self, preface_akn, node, regulation):
        for child in node:
            if ET.iselement(child):
                if child.tag == 'codetext':
                    self.process_preface_codetext(preface_akn, child)
                elif child.tag == 'currency':
                    comment_node = self.add_comment_node(preface_akn)
                    self.copy_text(comment_node, child)
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

    def copy_text(self, akn_node, cm_node):
        akn_node.text = cm_node.text
        if cm_node.tail:
            akn_node.tail = cm_node.tail

    def process_superscript(self, parent_akn, node):
        supnode = create_node('sup', parent_akn)
        self.copy_text(supnode, node)

    def process_underscore(self, parent_akn, node):
        unode = create_node('u', parent_akn)
        self.copy_text(unode, node)

    def process_subscript(self, parent_akn, node):
        subnode = create_node('sub', parent_akn)
        self.copy_text(subnode, node)

    def process_bold(self, parent_akn, node):
        boldnode = create_node('b', parent_akn)
        self.copy_text(boldnode, node)
    
    def process_italic(self, parent_akn, node):
        inode = create_node('i', parent_akn)
        self.copy_text(inode, node)

    def check_children(self, node):
        if len(node) > 0:
            print (ET.tostring(node))

    def process_filelink(self, parent_akn, node):
        filename = node.get('filename')
        if filename and re.search('(png|jpg|pdf|jpeg|gif)$', filename):
            filename = self.media_url + filename
            imgnode = create_node('img', parent_akn, {'src': filename})
            if node.tail:
                imgnode.tail = node.tail
        else:
            self.logger.warning('Unknown filelink: %s', ET.tostring(node))

    def process_para(self, parent_akn, node, section_akn = None, section_eid = None):
        pnode = create_node('p', parent_akn)
        pnode.text = node.text

        subsection = 1
        for  child in node:
            if ET.iselement(child):
                if child.tag == 'bold':
                    self.process_bold(pnode, child)
                elif child.tag == 'italic':
                    self.process_italic(pnode, child)
                elif child.tag == 'superscript':
                    self.process_superscript(pnode, child)
                elif child.tag == 'subscript':
                    self.process_subscript(pnode, child)
                elif child.tag == 'subsect':
                    if section_eid != None:
                        subsection_eid = '%s__subsec_%d' % (section_eid, subsection)
                        subsection += 1
                    else:
                        subsection_eid = None
                    self.process_subsection(section_akn, child, subsection_eid)
                elif child.tag == 'table' or child.tag == 'TABLE':
                    self.process_table(pnode, child)
                elif child.tag == 'filelink':
                    self.process_filelink(pnode, child)
                elif child.tag == 'ulink':
                    self.process_ulink(pnode, child)
                elif child.tag == 'codecitation':
                    self.process_codecitation(pnode, child)
                elif child.tag == 'underscore':
                    self.process_underscore(pnode, child)
                elif child.tag == 'actcitation':
                    self.process_actcitation(pnode, child)
                elif child.tag == 'actseccitation':
                    self.process_actcitation(pnode, child)
                elif child.tag == 'strike':
                    if child.tail:
                        pnode.text +=  child.tail
                else:
                    self.logger.warning ('Ignored element in para %s', ET.tostring(child))
            else:       
                self.logger.warning ('Ignored node in para %s', child)
        return pnode

    def process_ulink(self, parent_akn, node):
        anode = create_node('a', parent_akn, {'href': node.get('url')})
        self.copy_text(anode, node)

    def process_table(self, parent_akn, node):
        table_akn = create_node('table', parent_akn, node.attrib)
        for child in node:
            if ET.iselement(child):
                if child.tag == 'tr' or child.tag == 'TR':
                    self.process_tr(table_akn, child)
                elif child.tag == 'td' or child.tag == 'TD':
                    self.process_td(table_akn, child)
                elif child.tag == 'content':
                    trnode = create_node('tr', table_akn)
                    self.process_table_content(trnode, child)
                elif child.tag == 'tbody' or child.tag == 'TBODY':
                    self.process_tbody(table_akn, child)
                elif child.tag == 'table' or child.tag == 'TABLE':
                    self.process_table(table_akn, child)
                elif child.tag in ['number', 'name']:
                    trnode = create_node('tr', table_akn)
                    trnode.text = child.text
                elif child.tag == 'version':
                    pass
                else:    
                    self.logger.warning ('Ignored element in table %s', ET.tostring(child))
            else:       
                self.logger.warning ('Ignored node in table %s', child)

    def process_tbody(self, parent_akn, node):
        tbody_akn = create_node('tbody', parent_akn, node.attrib)
        for child in node:
            if ET.iselement(child):
                if child.tag == 'tr' or child.tag == 'TR':
                    self.process_tr(tbody_akn, child)
                elif child.tag == 'td' or child.tag == 'TD':
                    self.process_td(tbody_akn, child)
                elif child.tag == 'table' or child.tag == 'TABLE':
                    self.process_table(tbody_akn, child)
                else:    
                    self.logger.warning ('Ignored element in tbody %s', child.tag)
            else:       
                self.logger.warning ('Ignored node in tbody %s', child)

    def process_tr(self, parent_akn, node):
        tr_akn = create_node('tr', parent_akn, node.attrib)
        for child in node:
            if ET.iselement(child):
                if child.tag == 'td' or child.tag == 'TD':
                    self.process_td(tr_akn, child)
                elif child.tag == 'table' or child.tag == 'TABLE':
                    self.process_table(tr_akn, child)
                else:    
                    self.logger.warning ('Ignored element in tr %s', child.tag)
            else:       
                self.logger.warning ('Ignored node in tr %s', child)

    def process_td(self, parent_akn, node):
        td_akn = create_node('td', parent_akn, node.attrib)
        self.copy_text(td_akn, node)
        for child in node:
            if ET.iselement(child):
                if child.tag == 'td' or child.tag == 'TD':
                    self.process_td(td_akn, child)
                elif child.tag == 'table' or child.tag == 'TABLE':
                    self.process_table(td_akn, child)
                elif child.tag == 'ulink':
                    self.process_ulink(td_akn, child)
                elif child.tag == 'superscript':
                    self.process_superscript(td_akn, child)
                elif child.tag == 'para':
                    self.process_para(td_akn, child)
                elif child.tag == 'bold':
                    self.process_bold(td_akn, child)
                elif child.tag == 'subscript':
                    self.process_subscript(td_akn, child)
                elif child.tag == 'superscript':
                    self.process_superscript(td_akn, child)
                elif child.tag == 'underscore':
                    self.process_underscore(td_akn, child)
                elif child.tag == 'codecitation':
                    self.process_codecitation(td_akn, child)
                elif child.tag == 'actcitation':
                    self.process_actcitation(td_akn, child)
                elif child.tag == 'italic':
                    self.process_italic(td_akn, child)
                elif child.tag == 'filelink':
                    self.process_filelink(td_akn, child)
                else:    
                    self.logger.warning ('Ignored element in td %s', child.tag)
            else:       
                self.logger.warning ('Ignored node in td %s', child)

    def process_chapter(self, body_akn, node, regulation):
        eId = 'chap_%d' % regulation.chapnum
        chap_akn = create_node('chapter', body_akn, {'eId': eId})
        regulation.chapnum += 1

        subchap     = 1
        content_num = 1

        for child in node:
            if ET.iselement(child):
                if child.tag == 'code' and child.get('type') == 'Section':
                    self.process_section(chap_akn, child, regulation)
                elif child.tag == 'code' and child.get('type') == 'Article':
                    self.process_article(chap_akn, child, regulation)
                elif child.tag == 'code' and child.get('type') == 'Part':
                    self.process_part(chap_akn, child, regulation)
                elif child.tag == 'code' and child.get('type') == 'Table':
                    self.process_table(chap_akn, child)
                elif child.tag == 'code' and (child.get('type') == 'Subchapter' or child.get('type') == 'Undesignated' or child.get('type') == 'Unprefixed'):
                    subchap_eId = '%s_subchap_%d' % (eId, subchap)
                    subchap += 1
                    self.process_subchapter(chap_akn, child, regulation, subchap_eId)
                elif child.tag == 'version':
                    pass
                elif child.tag == 'number':
                    regulation.set_subnum(child.text)
                    self.process_number(chap_akn, child)
                elif child.tag == 'name':
                   self.process_heading(chap_akn, child)
                elif child.tag == 'code' and child.get('type')=='Appendix':
                    self.process_appendix(chap_akn, child, regulation)
                elif child.tag == 'content' or (child.tag == 'code' and child.get('type')=='Exhibit'):
                    content_eid = '%s__hcontainer_%d' % (eId, content_num)
                    content_num += 1
                    self.process_content(chap_akn, child, content_eid, eId, regulation)
                elif child.tag == 'code' and child.get('type')=='Group':
                    self.process_group(chap_akn, child, regulation)
                else:    
                   self.logger.warning ('Ignored element in chapter %s', ET.tostring(child))
            else:       
                self.logger.warning ('Ignored node in chapter %s', child)

    def process_subchapter(self, chap_akn, node, regulation, eId):
        subchap_akn = create_node('subchapter', chap_akn, {'eId': eId})

        content_num = 1
        subchap     = 1
        subarticle  = 1

        for child in node:
            if ET.iselement(child):
                if child.tag == 'code' and child.get('type') == 'Section':
                    self.process_section(subchap_akn, child, regulation)
                elif child.tag == 'code' and child.get('type') == 'Article':
                    self.process_article(subchap_akn, child, regulation)
                elif child.tag == 'code' and child.get('type')=='Appendix':
                    self.process_appendix(subchap_akn, child, regulation)
                elif child.tag == 'code' and child.get('type')=='Group':
                    self.process_group(subchap_akn, child, regulation)
                elif child.tag == 'code' and child.get('type')=='Undesignated':
                    subchap_eid = '%s_subchap_%d' % (eId, subchap)
                    subchap += 1
                    self.process_subchapter(chap_akn, child, regulation, subchap_eid)
                elif child.tag == 'code' and child.get('type')=='Subarticle':
                    subart_eid = '%s_subarticle_%d' % (eId, subarticle)
                    subarticle += 1
                    self.process_subarticle(subchap_akn, child, regulation, subart_eid)
                elif child.tag == 'number':
                    self.process_number(subchap_akn, child)
                elif child.tag == 'name':
                   self.process_heading(subchap_akn, child)
                elif child.tag == 'content':
                    content_eid = '%s__hcontainer_%d' % (eId, content_num)
                    content_num += 1
                    self.process_content(subchap_akn, child, content_eid, eId, regulation)
                elif child.tag == 'version':
                    pass
                else:    
                   self.logger.warning ('Ignored element in subchapter %s', ET.tostring(child))
            else:       
                self.logger.warning ('Ignored node in subchapter %s', child)


    def process_group(self, chap_akn, node, regulation):
        hcontent_akn = create_node('hcontainer', chap_akn)
        content_akn  = create_node('content', hcontent_akn)
        for child in node:
            if ET.iselement(child):
                if child.tag == 'code' and child.get('type') == 'Section':
                    self.process_section(content_akn, child, regulation)
                elif child.tag == 'code' and child.get('type') == 'Article':
                    self.process_article(content_akn, child, regulation)
                elif child.tag == 'code' and child.get('type')=='Appendix':
                    self.process_appendix(content_akn, child, regulation)
                elif child.tag == 'code' and child.get('type')=='Subgroup':
                    self.process_group(content_akn, child, regulation)
                elif child.tag == 'number':
                    self.process_number(content_akn, child)
                elif child.tag == 'name':
                   self.process_heading(content_akn, child)
                else:    
                   self.logger.warning ('Ignored element in group %s', ET.tostring(child))
            else:       
                self.logger.warning ('Ignored node in group %s', child)

    def process_subcode(self, body_akn, node, regulation):
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
                    elif codetype == 'Subpart':    
                        subpart_eid = 'subpart_%d' % regulation.subpart
                        regulation.subpart += 1   
                        self.process_subpart(body_akn, subpart_eid, child, regulation)
                    elif  codetype =='Appendix':
                        self.process_appendix(body_akn, child, regulation)
                    elif codetype == 'Undesignated':
                        self.process_subcode(body_akn, child, regulation)
                    else:
                        self.logger.warning('Ignored code element in subcode %s %s', codetype, ET.tostring(child))
                elif child.tag == 'name':
                    pnode = create_node('p', body_akn, {'class': 'heading'})
                    pnode.text = child.text
                elif child.tag == 'content':
                    content_eid = 'hcontainer_%s' % regulation.contentnum
                    regulation.contentnum += 1
                    self.process_content(body_akn, child, content_eid, '', regulation)
                else:    
                    self.logger.warning ('Ignored element in subcode %s', child.tag)
            else:       
                self.logger.warning ('Ignored node in subcode %s', child)

    def process_appendix(self, parent_akn, node, regulation):
        eId = 'hcontainer_%d' % regulation.contentnum
        regulation.contentnum += 1

        hcontent_akn = create_node('hcontainer', parent_akn, {'eId': eId})
        for child in node:
            if ET.iselement(child):
                if child.tag == 'name':
                    self.process_heading(hcontent_akn, child)
                elif child.tag == 'number':
                    self.process_number(hcontent_akn, child)
                elif child.tag == 'currency':
                    comment_node = self.add_comment_node(hcontent_akn)
                    comment_node.text = child.text
                elif child.tag == 'version':
                    pass
                elif child.tag == 'para':
                    self.process_para(hcontent_akn, child)
                elif child.tag == 'content':
                    self.process_appendix_content(hcontent_akn, child, regulation)
                elif child.tag == 'code' and child.get('type')=='Appendix':
                    self.process_appendix(hcontent_akn, child, regulation)
                else:    
                    self.logger.warning ('Ignored element in appendix %s', ET.tostring(child))
            else:
                self.logger.warning('Ignoring node in appendix %s', child)

    def process_appendix_content(self, parent_akn, node, regulation):
        eId = 'hcontainer_%d' % regulation.contentnum
        regulation.contentnum += 1

        hcontent_akn = create_node('hcontainer', parent_akn, {'eId': eId})
        content_akn  = create_node('content', hcontent_akn)

        for child in node:
            if ET.iselement(child):
                if child.tag == 'currency':
                    comment_node = self.add_comment_node(content_akn)
                    comment_node.text = child.text
                elif child.tag == 'codetext':    
                    self.process_appendix_codetext(content_akn, child, eId)
                elif child.tag == 'notes':
                    self.process_notes(content_akn, child)
                else:    
                    self.logger.warning ('Ignored element in appendix_content %s', child.tag)
            else:       
                self.logger.warning ('Ignored node in appendix_content %s', child)

    def process_appendix_codetext(self, content_akn, node, eId):
        subsection = 1
        for child in node:
            if ET.iselement(child):
                if child.tag =='para':
                    self.process_para(content_akn, child)
                elif child.tag == 'subsect':
                    subsection_eid = '%s_subsect_%d' % (eId, subsection)
                    subsection += 1
                    self.process_subsection(content_akn, child, subsection_eid)
                else:    
                    self.logger.warning ('Ignored element in appendix_codetext %s', child.tag)
            else:       
                self.logger.warning ('Ignored node in appendix_codetext %s', child)
        
    def process_part(self, body_akn, node, regulation):
        part_eid = 'part_%d' % regulation.partnum
        part_akn = create_node('part', body_akn,  {'eId': part_eid})
        regulation.partnum += 1

        subpart = 1
        content_num = 1
        for child in node:
            if ET.iselement(child):
                if child.tag == 'code' and child.get('type') == 'Section':
                    self.process_section(part_akn, child, regulation)
                elif child.tag == 'number':
                    self.process_number(part_akn, child)
                elif child.tag == 'name':
                    self.process_heading(part_akn, child)
                elif child.tag == 'content':
                    content_eid = '%s__hcontainer_%d' % (part_eid, content_num)
                    content_num += 1
                    self.process_content(part_akn, child, content_eid, part_eid, regulation)
                elif child.tag == 'code' and child.get('type')=='Undesignated':
                    self.process_part(body_akn, child, regulation)
                elif child.tag == 'code' and child.get('type')=='Chapter':
                    self.process_chapter(part_akn, child, regulation)
                elif child.tag == 'code' and child.get('type')=='Subpart':
                    subpart_eid = '%s__subpart_%d' % (part_eid, subpart)
                    self.process_subpart(part_akn, subpart_eid, child, regulation)
                    subpart += 1
                elif child.tag == 'code' and child.get('type')=='Appendix':
                    self.process_appendix(part_akn, child, regulation)
                elif child.tag == 'code' and child.get('type') == 'Article':
                    self.process_article(part_akn, child, regulation)
                elif child.tag == 'version':
                    pass
                else:    
                    self.logger.warning ('Ignored element in part %s', ET.tostring(child))
            else:       
                self.logger.warning ('Ignored node in part %s', child)

    def process_subpart(self, part_akn, subpart_eid, node, regulation):
        subpart_akn = create_node('subpart', part_akn,  {'eId': subpart_eid})
        content_num = 1
        for child in node:
            if ET.iselement(child):
                if child.tag == 'code' and child.get('type') == 'Section':
                    self.process_section(subpart_akn, child, regulation)
                elif child.tag == 'version':
                    pass
                elif child.tag == 'number':
                    self.process_number(subpart_akn, child)
                elif child.tag == 'name':
                    self.process_heading(subpart_akn, child)
                elif child.tag == 'code' and child.get('type')=='Undesignated':
                    self.process_part(subpart_akn, child, regulation)
                elif child.tag == 'content':
                    content_eid = '%s__hcontainer_%d' % (subpart_eid, content_num)
                    content_num += 1
                    self.process_content(subpart_akn, child, content_eid, subpart_eid, regulation)
                else:    
                    self.logger.warning ('Ignored element in subpart %s', ET.tostring(child))
            else:       
                self.logger.warning ('Ignored node in subpart %s', child)


    def add_comment_node(self, parent):
        comment_node = create_node('remark', parent, {'status': 'editorial'})
        return comment_node

    def process_notes(self, parent_akn, node):
        comment_node = self.add_comment_node(parent_akn)

        for child in node:
            if ET.iselement(child):
                if child.tag == 'notes-citeas':
                    self.process_citeas_notes(parent_akn, child)
                elif child.tag == 'notes-history':
                    self.process_notes_history(comment_node, child)
                elif child.tag == 'notes-maint':
                    self.process_notes_maint(comment_node, child)
                elif child.tag == 'notes-std':    
                    self.process_notes_std(comment_node, child)
                elif child.tag == 'notes-alert':    
                    self.process_notes_std(comment_node, child)
                elif child.tag == 'notes-editor':    
                    self.process_notes_std(comment_node, child)
                elif child.tag == 'notes-src':    
                    self.process_notes_std(comment_node, child)
                elif child.tag == 'notes-cr':    
                    self.process_notes_std(comment_node, child)
                else:    
                    self.logger.warning ('Ignored element in notes %s', ET.tostring(child))
            else:       
                self.logger.warning ('Ignored node in notes %s', child)

    def process_notes_history(self, comment_node, node):
       for child in node:
            if ET.iselement(child):
                if child.tag == 'note':
                    self.process_note(comment_node, child)
                else:    
                    self.logger.warning ('Ignored element in notes-history %s', child.tag)
            else:       
                self.logger.warning ('Ignored node in notes-history %s', child)

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
        citenode = create_node('neutralCitation', comment_node) 
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

 
    def process_codesec(self, parent_akn, node, state, title):
        if state == 'MI':
            text = node.get('use')
        else:
            text = node.text

        citenode = create_node('ref', parent_akn, {'href': ''})
        if text:
            citenode.attrib['use'] = text

        if state == 'CA':
            citenode.attrib['title'] = title

        text = ET.tostring(node, method = 'text', encoding = 'unicode')
        citenode.text = text

    def process_codecitation(self, parent_akn, node):
        span_akn = create_node('span', parent_akn)

        datatype = node.get('datatype')
        state = node.get('statecd')
        title = node.get('title')
        if datatype == 'D' and (state != 'CA' or title != None ) and state == self.statecd:
            self.copy_text(span_akn, node)

            for child in node:
                if ET.iselement(child):
                    if child.tag == 'codesec':
                        self.process_codesec(span_akn, child, state, title)
                    else:    
                        self.logger.warning ('Ignored element in codesec %s', child.tag)
                else:       
                    self.logger.warning ('Ignored node in codesec %s', child)
        else:
            span_akn.text =  ET.tostring(node, method = 'text', encoding = 'unicode')
            span_akn.tail = node.tail

    def process_actcitation(self, parent_akn, node):
        span_akn = create_node('span', parent_akn)
        text = []
        for child in node:
            if ET.iselement(child):
                if child.text:
                    text.append(child.text)

                if child.tail:
                    text.append(child.tail)
            else:       
                 self.logger.warning ('Ignored node in actcitation %s', child)
        span_akn.text = ''.join(text)
        if node.tail:
            span_akn.tail = node.tail

    def process_actid(self, parent_akn, node):
        anode = create_node('a', parent_akn, {'href': ''})
        self.copy_text(anode, node)

    def get_akn_date(self, datestr):
        ds = re.findall('\d+', datestr)
        return '%s-%s-%s' % (ds[2], ds[0], ds[1])

    def process_date(self, parent_akn, node, datestr, refersTo):
        datenode = create_node('date', parent_akn, {'date': datestr, \
                                                    'refersTo': refersTo})
        self.copy_text(datenode, node)

    def process_regcitation(self, parent_akn, node):
        href = self.media_url + node.get('filename')
        anode = create_node('a', parent_akn, {'href': href})
        self.copy_text(anode, node)

    def process_strike(self, parent_akn, node):
        delnode = create_node('del', parent_akn)
        self.copy_text(delnode, node)

    def process_note(self, comment_node, node):
        for child in node:
            if ET.iselement(child):
                if child.tag == 'para':
                    self.process_para(comment_node, child) 
                elif child.tag == 'italic':     
                    self.process_italic(comment_node, child) 
                elif child.tag == 'codecitation':
                     self.process_codecitation(comment_node, child)
                elif child.tag == 'actcitation':
                    self.process_actcitation(comment_node, child)
                elif child.tag == 'actseccitation':
                    self.process_actcitation(comment_node, child)
                elif child.tag == 'table' or child.tag == 'TABLE':
                    self.process_table(comment_node, child)
                elif child.tag == 'effectivedate':
                     d = child.get('use')
                     if d == None:
                         d = child.text
                     datestr = self.get_akn_date(d)
                     self.process_date(comment_node, child, datestr, '#effectivedate')
                elif child.tag == 'operationaldate':
                     d = child.get('use')
                     if d == None:
                         d = child.text
                     datestr = self.get_akn_date(d)
                     self.process_date(comment_node, child, datestr, '#operationaldate')

                elif child.tag == 'regcitation':
                     self.process_regcitation(comment_node, child)
                elif child.tag == 'linebreak':
                     create_node('br', comment_node)
                elif child.tag == 'subscript':
                    self.process_subscript(comment_node, child)
                else:    
                    self.logger.warning ('Ignored element in note %s', ET.tostring(child))
            else:       
                 self.logger.warning ('Ignored node in note %s', child)

    def process_number(self, parent_akn, node):
        number_node = create_node('num', parent_akn)
        number_node.text = ET.tostring(node, method='text', encoding='unicode', with_tail=False)

    def process_heading(self, parent_akn, node):
        heading_node = create_node('heading', parent_akn)
        heading_node.text = ET.tostring(node, method='text', encoding='unicode', with_tail=False)

    def process_content(self, section_akn, node, eId, section_eid, regulation):
        hcontent_akn = create_node('hcontainer', section_akn, {'eId': eId})
        content_akn  = create_node('content', hcontent_akn)

        subsection   = 1
        content      = 1

        for child in node:
            if ET.iselement(child):
                if child.tag == 'currency':
                    comment_node = self.add_comment_node(content_akn)
                    comment_node.text = child.text
                    regulation.set_publish_date(child.text)
                elif child.tag == 'codetext':    
                    self.process_codetext(content_akn, child, section_akn, section_eid)
                elif child.tag == 'number':    
                   self.process_number(content_akn, child)
                elif child.tag == 'notes':
                    self.process_notes(content_akn, child)
                elif child.tag == 'subsect':
                    subsection_eid = '%s__subsec_%d' % (eId, subsection)
                    subsection += 1
                    self.process_subsection(section_akn, child, eId)
                elif child.tag == 'version':
                    pass
                elif child.tag == 'name':
                   self.process_heading(hcontent_akn, child)
                elif child.tag == 'content':
                   content += 1
                   subcontent_eid = '%s_content_%d' % (eId, content)
                   self.process_content(section_akn, child, subcontent_eid, section_eid, regulation)
                else:    
                    self.logger.warning ('Ignored element in content %s', ET.tostring(child))
            else:       
                self.logger.warning ('Ignored node in content %s', child)
                    
    def process_table_content(self, parent_akn, node):
        
        content_akn  = create_node('content', parent_akn)
        subsection   = 1

        for child in node:
            if ET.iselement(child):
                if child.tag == 'currency':
                    comment_node = self.add_comment_node(content_akn)
                    comment_node.text = child.text
                elif child.tag == 'notes':
                    self.process_notes(content_akn, child)
                elif child.tag == 'codetext':
                    self.process_codetext(content_akn, child, content_akn, None)
                else:    
                    self.logger.warning ('Ignored element in table_content %s', child.tag)
            else:       
                self.logger.warning ('Ignored node in table_content %s', child)
                    
       
    def process_codetext(self, parent_akn, node, section_akn, section_eid):
        subsection   = 1
        for child in node:
            if ET.iselement(child):
                if child.tag == 'para':
                    self.process_para(parent_akn, child, section_akn, section_eid)
                elif child.tag == 'subsect':
                    subsection_eid = '%s__subsec_%d' % (section_eid, subsection)
                    subsection += 1
                    self.process_subsection(section_akn, child, subsection_eid)
                else:    
                    self.logger.warning ('Ignored element in codetext %s', child.tag)
            else:       
                self.logger.warning ('Ignored node in codetext %s', child)
                    

    def process_article(self, parent_akn, node, regulation):
        eId = 'article_%d' % regulation.articlenum
        regulation.articlenum += 1
        content_num       = 1
        article_akn = create_node('article', parent_akn, {'eId': eId})

        subarticle = 1
        subchap = 1
        for child in node:
            if ET.iselement(child):
                if child.tag == 'number':
                   self.process_number(article_akn, child)
                   regulation.set_num(child.text)
                elif child.tag == 'name':
                   self.process_heading(article_akn, child)
                elif child.tag == 'table' or child.tag == 'TABLE':
                    self.process_table(article_akn, child)
                elif child.tag == 'code' and child.get('type') == 'Section':
                   self.process_section(article_akn, child, regulation)
                elif child.tag == 'code' and child.get('type') == 'Undesignated':
                   self.process_subcode(article_akn, child, regulation)
                elif child.tag == 'code' and child.get('type') == 'Appendix':
                    self.process_appendix(article_akn, child, regulation)
                elif child.tag == 'code' and child.get('type') == 'Table':
                    self.process_table(article_akn, child)
                elif child.tag == 'code' and child.get('type') in ['Subarticle', 
'Unprefixed']:
                    subart_eid = '%s_subarticle_%d' % (eId, subarticle)
                    subarticle += 1
                    self.process_subarticle(article_akn, child, regulation, subart_eid)
                elif child.tag == 'code' and child.get('type') == 'Part':
                    self.process_part(article_akn, child, regulation)
                elif child.tag == 'code' and child.get('type') == 'Addendum':
                    self.process_appendix(article_akn, child, regulation)
                elif child.tag == 'content':
                   content_eid = '%s__hcontainer_%d' % (eId, content_num)
                   self.process_content(article_akn, child, content_eid, eId, regulation)
                   content_num += 1
                elif child.tag == 'version':
                   # no idea what to do about the version tag
                   pass
                elif child.tag == 'notes':
                    self.process_notes(article_akn, child)
                elif child.tag == 'table' or child.tag == 'TABLE':
                    self.process_table(article_akn, child)
                elif child.tag == 'code' and child.get('type') == 'Subchapter':
                    subchap_eId = '%s_subchap_%d' % (eId, subchap)
                    subchap += 1
                    self.process_subchapter(article_akn, child, regulation, subchap_eId)
                else:    
                    self.logger.warning ('Ignored element in article %s', ET.tostring(child))
            else:       
                self.logger.warning ('Ignored node in article %s', child)

    def process_subarticle(self, parent_akn, node, regulation, eId):
        hcontent_akn = create_node('hcontainer', parent_akn, {'eId': eId})
        content_akn  = create_node('content', hcontent_akn)

        content_num = 1
        for child in node:
            if ET.iselement(child):
                if child.tag == 'number':
                   self.process_number(content_akn, child)
                elif child.tag == 'name':
                   self.process_heading(content_akn, child)
                elif child.tag == 'code' and child.get('type') == 'Section':
                   self.process_section(content_akn, child, regulation)
                elif child.tag == 'code' and child.get('type') == 'Undesignated':
                   self.process_subcode(content_akn, child, regulation)
                elif child.tag == 'code' and child.get('type') == 'Appendix':
                    self.process_appendix(content_akn, child, regulation)
                elif child.tag == 'code' and child.get('type') == 'Subarticle':
                    self.process_subarticle(content_akn, child, regulation)
                elif child.tag == 'code' and child.get('type') == 'Part':
                    self.process_part(content_akn, child, regulation)
                elif child.tag == 'code' or child.get('type') == 'Table':
                    self.process_table(content_akn, child)
                elif child.tag == 'table' or child.tag == 'TABLE':
                    self.process_table(content_akn, child)
                elif child.tag == 'content':
                   content_eid = '%s__hcontainer_%d' % (eId, content_num)
                   self.process_content(article_akn, child, content_eid, eId, regulation)
                   content_num += 1
                elif child.tag == 'version':
                   # no idea what to do about the version tag
                   pass
                elif child.tag == 'notes':
                    self.process_notes(content_akn, child)
                elif child.tag == 'table' or child.tag == 'TABLE':
                    self.process_table(content_akn, child)
                else:    
                    self.logger.warning ('Ignored element in subarticle %s %s', child.tag, child.get('type'))
            else:       
                self.logger.warning ('Ignored node in subarticle %s', child)

    def process_section(self, parent_akn, node, regulation):
        namenode = node.find('name')
        if namenode != None:
            text = ET.tostring(namenode, method='text', encoding='unicode', with_tail=False)
            if re.match('\s*\[?rescind', text, re.IGNORECASE):
                return

        eId = 'sec_%d' % regulation.secnum
        regulation.secnum += 1
        content_num       = 1
        subsection        = 1
        section_akn = create_node('section', parent_akn, {'eId': eId})

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
                   self.process_content(section_akn, child, content_eid, eId, regulation)
                   content_num += 1
                elif child.tag == 'version':
                   version_node = create_node('version', section_akn)
                   version_node.text = child.text
                elif child.tag == 'notes':
                    self.process_notes(section_akn, child)
                elif child.tag == 'code' and child.get('type')=='Appendix':
                    self.process_appendix(section_akn, child, regulation)
                else:    
                    self.logger.warning ('Ignored element in section %s', ET.tostring(child))
            else:       
                self.logger.warning ('Ignored node in section %s', child)


    def add_text(self, akn, node):
        if akn.text:
            akn.text += node.text
        else:
            akn.text = node.text

    def add_tail(self, akn, node):
        if akn.tail:
            akn.tail += node.tail
        else:
            akn.tail = node.tail

    def print_text(self, node):
        if node.text and node.text.strip():
            print ('TEXT', node.text, ET.tostring(node))

        if node.tail and node.tail.strip():
            print ('TAIL', node.tail, ET.tostring(node))

    def process_subsection(self, section_akn, node, eId):
        subsection_akn = create_node('subsection', section_akn)
        if eId:
            node.set('eId', eId)
        content_akn    = None
        subsection     = 1
        para_node      = None
        for child in node:
            if ET.iselement(child):
                if child.tag == 'designator':
                    self.process_number(subsection_akn, child)
                    content_akn = create_node('content', subsection_akn)
                    para_node = create_node('p', content_akn)
                    if child.tail:
                        para_node.text = child.tail
                elif child.tag == 'subsect':
                    subsection_eid = '%s__subsec_%d' % (eId, subsection)
                    subsection += 1
                    self.process_subsection(subsection_akn, child, subsection_eid)
                elif child.tag == 'codecitation':
                    self.process_codecitation(para_node, child)
                elif child.tag == 'para':
                    para_node = self.process_para(content_akn, child, \
                                section_akn = subsection_akn, section_eid = eId)
                elif child.tag == 'ulink':
                    self.process_ulink(para_node, child)
                elif child.tag == 'actcitation':
                    self.process_actcitation(para_node, child)
                elif child.tag == 'superscript':
                    if para_node == None:
                        self.process_superscript(subsection_akn, child)
                    else:
                        self.process_superscript(para_node, child)
                elif child.tag == 'subscript':
                    self.process_subscript(para_node, child)
                elif child.tag == 'bold':
                    self.process_bold(para_node, child)
                elif child.tag == 'underscore':
                    self.process_underscore(para_node, child)
                elif child.tag == 'italic':
                    self.process_italic(para_node, child)
                elif child.tag == 'strike':
                    self.process_strike(para_node, child)
                elif child.tag == 'actseccitation':
                    self.process_actcitation(para_node, child)
                elif child.tag == 'filelink':
                    self.process_filelink(para_node, child)
                elif child.tag == 'table' or child.tag == 'TABLE':
                    self.process_table(para_node, child)
                else:    
                    self.logger.warning ('Ignored element in subsection %s', ET.tostring(child))
                if child.tag not in ['designator', 'subsect', 'codecitation', 'para', 'ulink', 'actcitation', 'superscript', 'subscript', 'bold', 'underscore', 'italic', 'strike']:
                    if child.text:
                        self.add_text(para_node, child)

                    if child.tail:
                        self.add_tail(para_node, child)


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

    def get_frbr_uri(self):
        locality    = self.metadata.get_value('locality')
        country     = self.metadata.get_value('country')
        regyear     = self.metadata.get_value('regyear')
        regnum      = self.metadata.get_value('regnum')
        frbr_uri = '/akn/%s-%s/act/regulations/%s/%s' % (country, locality, regyear, regnum)
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
        content_num = 1
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
                    subdivision_eid = '%s__subdivision_%d' % (eId, subsection)
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

        nums = re.findall('\d+', text)
        if nums:
            self.metadata.set_value('regnum',  nums[0])
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

if __name__ == '__main__':
    indir    = sys.argv[1]
    outdir   = sys.argv[2]
    mediaurl = sys.argv[3]

    akn30 = Akn30(mediaurl)
    regulations = {}

    for filename in os.listdir(indir):
        #if filename != 'ca-2021-admin-title0028.xml':
        #    continue

        filepath = os.path.join(indir, filename)
        if os.path.isfile(filepath):
            akn30.process_casemaker(filepath, regulations)

    refresolver = RefResolver()
    for num, regulation in regulations.items():
        if num == None:
            continue

        refresolver.add_regulation(regulation) 

    for num, regulation in regulations.items():
        if num == None:
            continue

        refresolver.resolve(regulation)    

    for num, regulation in regulations.items():
        if num == None:
            continue

        filepath = os.path.join(outdir, '%s.xml' % num)
        regulation.write_akn_xml(filepath)
    
