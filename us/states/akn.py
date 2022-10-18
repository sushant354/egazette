import re
import os
import logging

import lxml.etree as ET
from .regulation import Regulation, create_node
from .states import title_states

class DTDResolver(ET.Resolver):
    def resolve(self, url, public_id, context):
        dirname = os.path.dirname(os.path.realpath(__file__))
        filename = os.path.join(dirname, 'HTMLLat2.ent')
        return self.resolve_filename(filename, context)

class FileInfo:
    def __init__(self, country):
        self.country   = country
        self.root_name = None
        self.dept_name = None
        self.org_name  = None

    def  __repr__(self):
        return 'root: %s, dept: %s, org: %s' % (self.root_name, self.dept_name, self.org_name)


class Akn30:
    def __init__(self, media_url):
        self.media_url  = media_url
        self.localities = {'MI': 'michigan'}
        self.logger     = logging.getLogger('akn30')
        self.statecd    = None
    

    def process_casemaker(self, xml_file, regulations):
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
                    if codetype == 'Title' or file_info.statecd in title_states:
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
                elif child.tag == 'code' and child.get('type') == 'Undesignated':
                    self.process_code(child, file_info, regulations)
                elif child.tag == 'name':
                    file_info.dept_name = child.text
                elif child.tag == 'code' and child.get('type') == 'Section':
                    self.process_section(div_akn, child, regulation)
                else:
                    self.logger.warning('Ignored element in dept %s', ET.tostring(child))
            else:       
                self.logger.warning ('Ignored node in dept %s', child)

    def process_code(self, node, file_info, regulations):
        regulation = self.process_regulation(file_info, node)
        num = regulation.get_num()
        if not num:
            self.logger.warning ('NO NUM %s', regulation)
            return

        if regulation.statecd in title_states:
            title = regulation.get_title()
            num_u = num.upper()
            if regulation.statecd in ['AR', 'IA']:
                header = 'Agency'
            else:
                header = 'Title'
            if title:
                title = '%s %s - %s' % (header, num_u, title)
            else:   
                title = '%s %s' % (header, num_u)

            regulation.set_title(title)

        if num in regulations:
            print ('Num', num)
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

        if num1 == '' or num2 == '':
            self.logger.warning("Couldn't merge %s", reg1.get_num())
            return reg1


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
        regtype                = node.get('type')
        num      = None

        for child in node:
            if ET.iselement(child):
                if child.tag == 'version':
                    continue
                elif child.tag == 'number':
                    num = child.text
                    regulation.set_num(child.text)
                elif child.tag == 'code':
                    codetype =  child.get('type') 
                    if codetype == 'Section':
                        self.process_section(body_akn, child, regulation)
                    elif codetype in ['Rule', 'Rule2']:
                        if file_info.statecd in ['AR', 'CO', 'ID']:
                            self.process_chapter(body_akn, child, regulation)
                        else:    
                            self.process_section(body_akn, child, regulation)
                    elif codetype == 'Division':    
                        self.process_division(body_akn, child, regulation)
                    elif codetype == 'Chapter' or codetype == 'Subchapter':    
                        self.process_chapter(body_akn, child, regulation)
                    elif codetype in ['Part', 'Subpart', 'Regulation']:    
                        self.process_part(body_akn, child, regulation)
                    elif codetype in ['Undesignated', 'Unprefixed']:
                        self.process_group(body_akn, child, regulation)
                    elif codetype == 'RegulationNo':
                        self.process_division(body_akn, child, regulation)
                    elif codetype == 'Article' or codetype == 'Subarticle':
                        self.process_article(body_akn, child, regulation)
                    elif codetype == 'Appendix':
                        self.process_appendix(body_akn, child, regulation)
                    elif codetype in ['Subtitle', 'Title', 'Sec2']:
                        self.process_division(body_akn, child, regulation)
                    elif child.tag == 'code' and child.get('type') == 'Form':
                        self.process_group(body_akn, child, regulation)
                    else:    
                        self.logger.warning ('Ignored codetype in regulation %s', ET.tostring(child))
                elif child.tag == 'name':
                    regulation.set_title(self.get_name(child))
                    pnode = create_node('p', preface_akn, {'class': 'title'})
                    title = create_node('shortTitle', pnode)
                    if num != None and regtype != None:
                        short_title = '%s %s - %s' % (regtype, num, child.text)
                    else:
                        short_title = child.text
                    title.text = short_title
                elif child.tag == 'content':
                    self.process_preface(preface_akn, child, regulation)
                else:    
                    self.logger.warning ('Ignored element in regulation %s', ET.tostring(child))
            else:       
                self.logger.warning ('Ignored node in regulation %s', child)

        return regulation

    def get_name(self, node):
        name = node.text
        for child in node:
            if child.tail:
                if name:
                    name += child.tail
                else:
                    name = child.tail
        return name

    def process_division(self, parent_akn, node, regulation):
        eId = 'division_%d' % regulation.divnum
        regulation.divnum += 1
        div_akn = create_node('division', parent_akn, {'eId': eId})

        subdiv  = 1
        subchap = 1
        content_num = 1
        for child in node:
            if ET.iselement(child):
                if child.tag == 'code' and child.get('type') in ['Chapter', 'Rule2']:
                    self.process_chapter(div_akn, child, regulation)
                elif child.tag == 'code' and child.get('type') == 'Section':
                    self.process_section(div_akn, child, regulation)
                elif child.tag == 'code' and child.get('type') == 'Article':
                    self.process_article(div_akn, child, regulation)
                elif child.tag == 'code' and child.get('type')=='Undesignated':
                    self.process_part(div_akn, child, regulation)
                elif child.tag == 'code' and child.get('type') in ['Part', 'Regulation', 'Subpart']:
                    self.process_part(div_akn, child, regulation)
                elif child.tag == 'code' and child.get('type')=='Appendix':
                    self.process_appendix(div_akn, child, regulation)
                elif child.tag == 'code' and child.get('type') in ['Subdivision', 'Division']:
                    subdivision_eid = '%s_subdivision_%d' % (eId, subdiv)
                    subdiv += 1
                    self.process_subdivision(div_akn, child, regulation, subdivision_eid)
                elif child.tag == 'code' and child.get('type') == 'Subchapter':
                    subchap_eId = '%s_subchap_%d' % (eId, subchap)
                    subchap += 1
                    self.process_subchapter(div_akn, child, regulation, subchap_eId)
                elif child.tag == 'code' and child.get('type') == 'Rule':
                    self.process_section(div_akn, child, regulation)
                elif child.tag == 'number':
                    self.process_number(div_akn, child)
                    regulation.set_subnum(child.text)
                elif child.tag == 'name':
                   self.process_heading(div_akn, child)
                elif child.tag == 'content':
                    content_eid = '%s__hcontainer_%d' % (eId, content_num)
                    content_num += 1
                    self.process_content(div_akn, child, content_eid, eId, regulation)
                elif child.tag == 'code' and child.get('type') in ['Form', 'Attachment']:
                    self.process_group(div_akn, child, regulation)
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
                elif child.tag == 'code' and child.get('type') in['Part', 'Sec2']:
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
                    self.process_notes(preface_akn, child, None, regulation)
                else:    
                    self.logger.warning ('Ignored element in preface %s', child.tag)
            else:       
                self.logger.warning ('Ignored node in preface %s', child)

    def process_preface_codetext(self, preface_akn, node):
        for child in node:
            if ET.iselement(child):
                if child.tag == 'para':
                    self.process_para( preface_akn, child)
                elif child.tag == 'filelink':
                    self.process_filelink(preface_akn, child)
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
        if filename and re.search('(png|jpg|pdf|jpeg|gif|tif|bmp)$', filename):
            filename = self.media_url + filename
            imgnode = create_node('img', parent_akn, {'src': filename})
            if node.tail:
                imgnode.tail = node.tail
        elif filename and re.search('\.doc$', filename):
            url  = self.media_url + filename
            linknode = create_node('a', parent_akn, {'href': url})
            self.copy_text(linknode, node)
        elif filename and re.search('\.(htm|html|xls|rtf|xlsx)$', filename, re.IGNORECASE):
            url  = self.media_url + filename
            linknode = create_node('a', parent_akn, {'href': url})
            self.copy_text(linknode, node)
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
                        if pnode.text:
                            pnode.text +=  child.tail
                        else:
                            pnode.text = child.tail

                elif child.tag == 'effectivedate':
                    self.process_effective_date(pnode, child)
                elif child.tag == 'regcitation':
                     self.process_regcitation(pnode, child)
                elif child.tag == 'linebreak':    
                    create_node('br', pnode)
                elif child.tag == 'nbsp':
                    self.process_nbsp(pnode, child)
                elif child.tag == 'li':
                     if child.text:
                         self.add_text(pnode, child)
                     if child.tail:
                         if pnode.text:
                             pnode.text += child.tail
                         else:
                             pnode.text = child.tail
                elif child.tag == 'footnoteref':
                    self.process_footnoteref(pnode, child)
                elif child.tag == 'add':    
                    self.process_add(pnode, child, section_eid)
                elif child.tag == 'del':
                    self.process_strike(pnode, child)
                elif child.tag == 'monospace':
                    self.process_monospace(pnode, child)
                else:
                    self.logger.warning ('Ignored element in para %s', ET.tostring(child))
            else:       
                self.logger.warning ('Ignored node in para %s', child)
        return pnode

    def process_nbsp(self, pnode, child):
        if pnode.text:
            pnode.text += ' ' 
        else:    
            pnode.text = ' ' 
        if child.text:
            pnode.text += child.text
        if child.tail:
            pnode.text += child.tail


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
                elif child.tag == 'thead' or child.tag == 'THEAD':
                    self.process_thead(table_akn, child)
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

    def process_thead(self, parent_akn, node):
        tbody_akn = create_node('thead', parent_akn, node.attrib)
        for child in node:
            if ET.iselement(child):
                if child.tag == 'tr' or child.tag == 'TR':
                    self.process_tr(tbody_akn, child)
                else:    
                    self.logger.warning ('Ignored element in thead %s', child.tag)
            else:       
                self.logger.warning ('Ignored node in thead %s', child)


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
                elif child.tag == 'th' or child.tag == 'TH':
                    self.process_th(tr_akn, child)
                elif child.tag == 'table' or child.tag == 'TABLE':
                    self.process_table(tr_akn, child)
                else:    
                    self.logger.warning ('Ignored element in tr %s', child.tag)
            else:       
                self.logger.warning ('Ignored node in tr %s', child)

    def process_th(self, parent_akn, node):
        th_akn = create_node('th', parent_akn, node.attrib)
        self.copy_text(th_akn, node)
        for child in node:
            if child.tag == 'bold':
                self.process_bold(th_akn, child)
            elif child.tag == 'superscript':
                self.process_superscript(th_akn, child)
            else:    
                self.logger.warning ('Ignored node in th %s', child)

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
                elif child.tag == 'linebreak':    
                    create_node('br', td_akn)
                elif child.tag == 'strike':
                    self.process_strike(td_akn, child)
                elif child.tag == 'add':    
                    self.process_add(td_akn, child, None)
                elif child.tag == 'actseccitation':
                    self.process_actcitation(td_akn, child)
                elif child.tag == 'itemizedlist':
                    self.process_list(td_akn, child)
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
        subpart     = 1

        for child in node:
            
            if ET.iselement(child):
                if child.tag == 'code' and child.get('type') == 'Section':
                    self.process_section(chap_akn, child, regulation)
                elif child.tag == 'code' and child.get('type') == 'Article':
                    self.process_article(chap_akn, child, regulation)
                elif child.tag == 'code' and child.get('type') == 'Chapter':
                    self.process_chapter(body_akn, child, regulation)
                elif child.tag == 'code' and child.get('type') in ['Part', 'Sec2', 'Regulation', 'Rule2']:
                    self.process_part(chap_akn, child, regulation)
                elif child.tag == 'code' and child.get('type') == 'Table':
                    self.process_group(chap_akn, child, regulation)
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
                elif child.tag == 'code' and child.get('type')in ['Group', 'Figure', 'Form', 'Subsection']:
                    self.process_group(chap_akn, child, regulation)
                elif child.tag == 'code' and child.get('type') == 'Rule':
                    has_article = child.find("code[@type='Article']")
                    has_section = child.find("code[@type='Section']")
                    if has_article == None and has_section == None:
                        self.process_section(chap_akn, child, regulation)
                    else:    
                        self.process_group(chap_akn, child, regulation)

                elif child.tag == 'code' and child.get('type') == 'Subject':
                    self.process_part(chap_akn, child, regulation)
                elif child.tag == 'code' and child.get('type')=='Subpart':
                    subpart_eid = '%s__subpart_%d' % (eId, subpart)
                    self.process_subpart(chap_akn, subpart_eid, child, regulation)
                    subpart += 1
                elif child.tag == 'code' and child.get('type')in ['Attachment', 'Addendum', 'Schedule', 'Chart', 'Amendment']:
                    self.process_group(chap_akn, child, regulation)
                elif child.tag == 'code' and child.get('type')=='Division':
                    self.process_division(chap_akn, child, regulation)
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
                elif child.tag == 'code' and child.get('type')=='Division':
                    self.process_division(subchap_akn, child, regulation)
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
                elif child.tag == 'content' or (child.tag == 'code' and child.get('type')=='Exhibit'):
                    content_eid = '%s__hcontainer_%d' % (eId, content_num)
                    content_num += 1
                    self.process_content(subchap_akn, child, content_eid, eId, regulation)
                elif child.tag == 'code' and child.get('type') in ['Rule', 'Canon']:
                    self.process_section(subchap_akn, child, regulation)
                elif child.tag == 'version':
                    pass
                elif child.tag == 'code' and child.get('type')=='Unprefixed':
                    self.process_part(subchap_akn, child, regulation)
                elif child.tag == 'code' and child.get('type') in ['Part', 'Sec2', 'Subpart']:
                    self.process_part(subchap_akn, child, regulation)
                elif child.tag == 'code' and child.get('type')in ['Form', 'Attachment', 'Table', 'Subchapter']:
                    self.process_group(subchap_akn, child, regulation)
                else:
                   self.logger.warning ('Ignored element in subchapter %s', ET.tostring(child))
            else:       
                self.logger.warning ('Ignored node in subchapter %s', child)


    def process_group(self, chap_akn, node, regulation):
        hcontent_akn = create_node('hcontainer', chap_akn)
        prefix       = node.get('type')
        if prefix in ['Undesignated', 'Unprefixed']:
            prefix = None

        for child in node:
            if ET.iselement(child):
                if child.tag == 'code' and child.get('type') in ['Section', 'Sec2']:
                    self.process_section(hcontent_akn, child, regulation)
                elif child.tag == 'code' and child.get('type') == 'Article':
                    self.process_article(hcontent_akn, child, regulation)
                elif child.tag == 'code' and child.get('type')=='Appendix':
                    self.process_appendix(hcontent_akn, child, regulation)
                elif child.tag == 'code' and child.get('type')=='Subgroup':
                    self.process_group(hcontent_akn, child, regulation)
                elif child.tag == 'code' and child.get('type') in ['Exhibit', 'Schedule', 'Undesignated', 'Unprefixed', 'Form', 'Attachment', 'Rule']:
                    self.process_group(hcontent_akn, child, regulation)
                elif child.tag == 'number':
                    self.process_number(hcontent_akn, child)
                elif child.tag == 'name':
                    self.process_heading(hcontent_akn, child, prefix = prefix)
                elif child.tag == 'version':
                    pass
                elif child.tag == 'content':
                    content_eid = 'hcontainer_%s' % regulation.contentnum
                    regulation.contentnum += 1
                    self.process_content(hcontent_akn, child, content_eid, '', regulation)
                elif child.tag == 'code' and child.get('type')in ['Part', 'Subpart']:
                    self.process_part(hcontent_akn, child, regulation)
                elif child.tag == 'code' and child.get('type') in ['Chapter', 'Subchapter']:
                    self.process_chapter(hcontent_akn, child, regulation)
                elif child.tag == 'code' and child.get('type') == 'Subtitle':
                        self.process_division(hcontent_akn, child, regulation)
                elif child.tag == 'code' and child.get('type')=='Division':
                    self.process_division(hcontent_akn, child, regulation)
                else:    
                   self.logger.warning ('Ignored element in group %s', ET.tostring(child))
            else:       
                self.logger.warning ('Ignored node in group %s', child)

    def process_subcode(self, body_akn, node, regulation):
        for child in node:
            if ET.iselement(child):
                if child.tag == 'version':
                    continue
                elif child.tag == 'number':
                    self.process_number(body_akn, child)
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
                    elif codetype in ['Undesignated', 'Unprefixed']:
                        self.process_subcode(body_akn, child, regulation)
                    elif  codetype in ['Opinion', 'Schedule', 'Exhibit', 'Form', 'Attachment']:
                        self.process_group(body_akn, child, regulation)
                    elif child.tag == 'code' and child.get('type') == 'Article':
                        self.process_article(body_akn, child, regulation)
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
                elif child.tag == 'code' and (child.get('type')=='Appendix' or child.get('style')=='Appendix'):
                    self.process_appendix(hcontent_akn, child, regulation)
                elif child.tag == 'code' and child.get('type') in ['Form', 'Chart', 'Unprefixed', 'Exhibit', 'Title', 'Attachment', 'Addendum', 'Schedule']:
                    self.process_group(hcontent_akn, child, regulation)
                elif child.tag == 'code' and child.get('type') in ['Rule', 'Section']:
                    self.process_section(hcontent_akn, child, regulation)
                elif child.tag == 'code' and child.get('type')  == 'Undesignated':
                    self.process_part(hcontent_akn, child, regulation)
                elif child.tag == 'code' and child.get('type') == 'Table':
                    self.process_group(hcontent_akn, child, regulation)
                elif child.tag == 'code' and child.get('type')=='Chapter':
                    self.process_chapter(hcontent_akn, child, regulation)
                elif child.tag == 'code' and child.get('type') == 'Part':
                    self.process_part(hcontent_akn, child, regulation)
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
                    self.process_notes(content_akn, child, eId, regulation)
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
                elif child.tag == 'table' or child.tag == 'TABLE':
                    self.process_table(content_akn, child)
                elif child.tag == 'literallayout':
                    self.process_pre(content_akn, child)
                elif child.tag == 'table' or child.tag == 'TABLE':
                    self.process_table(content_akn, child)
                elif child.tag == 'bold':
                    self.process_bold(content_akn, child)
                elif child.tag == 'itemizedlist':
                    self.process_list(content_akn, child)
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
                if child.tag == 'code' and child.get('type') in ['Section', 'Regulation']:
                    self.process_section(part_akn, child, regulation)
                elif child.tag == 'number':
                    self.process_number(part_akn, child)
                elif child.tag == 'name':
                    self.process_heading(part_akn, child)
                elif child.tag == 'content' or (child.tag == 'code' and child.get('type')=='Exhibit'):
                    content_eid = '%s__hcontainer_%d' % (part_eid, content_num)
                    content_num += 1
                    self.process_content(part_akn, child, content_eid, part_eid, regulation)
                elif child.tag == 'code' and child.get('type')=='Undesignated':
                    self.process_part(body_akn, child, regulation)
                elif child.tag == 'code' and child.get('type')=='Chapter':
                    self.process_chapter(part_akn, child, regulation)
                elif child.tag == 'code' and child.get('type') in ['Subpart', 'Rule2', 'Unprefixed', 'Part', 'Title', 'Sec2', 'Subtitle', 'Subsection']:
                    subpart_eid = '%s__subpart_%d' % (part_eid, subpart)
                    self.process_subpart(part_akn, subpart_eid, child, regulation)
                    subpart += 1
                elif child.tag == 'code' and child.get('type')=='Appendix':
                    self.process_appendix(part_akn, child, regulation)
                elif child.tag == 'code' and child.get('type') == 'Article':
                    self.process_article(part_akn, child, regulation)
                elif child.tag == 'code' and child.get('type') == 'Rule':
                    self.process_section(part_akn, child, regulation)
                elif child.tag == 'code' and child.get('type') in ['Form', 'Figure', 'Attachment', 'Table', 'Schedule']:
                    self.process_group(part_akn, child, regulation)
                elif child.tag == 'version':
                    pass
                else:    
                    self.logger.warning ('Ignored element in part %s', ET.tostring(child))
            else:       
                self.logger.warning ('Ignored node in part %s', child)

    def process_subpart(self, part_akn, subpart_eid, node, regulation):
        subpart_akn = create_node('subpart', part_akn,  {'eId': subpart_eid})
        content_num = 1
        subpart     = 1
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
                elif child.tag == 'code' and child.get('type') in ['Chapter', 'Subchapter']:    
                    self.process_chapter(subpart_akn, child, regulation)
                elif child.tag == 'code' and child.get('type') == 'Article':
                    self.process_article(subpart_akn, child, regulation)
                elif child.tag == 'code' and child.get('type') == 'Rule':
                    self.process_section(subpart_akn, child, regulation)
                elif child.tag == 'code' and child.get('type') in ['Unprefixed', 'Table', 'Exhibit', 'Schedule']:
                    self.process_group(subpart_akn, child, regulation)
                elif child.tag == 'code' and child.get('type') == 'Appendix':
                    self.process_appendix(subpart_akn, child, regulation)
                elif child.tag == 'code' and child.get('type') == 'Sec2':
                    self.process_group(subpart_akn, child, regulation)
                elif child.tag == 'code' and child.get('type')=='Subpart':
                    subsubpart_eid = '%s__subpart_%d' % (subpart_eid, subpart)
                    self.process_subpart(subpart_akn, subsubpart_eid, child, regulation)
                    subpart += 1
                else:    
                    self.logger.warning ('Ignored element in subpart %s', ET.tostring(child))
            else:       
                self.logger.warning ('Ignored node in subpart %s', child)


    def add_comment_node(self, parent):
        comment_node = create_node('remark', parent, {'status': 'editorial'})
        return comment_node

    def process_notes(self, parent_akn, node, eId, regulation):
        comment_node = self.add_comment_node(parent_akn)

        for child in node:
            if ET.iselement(child):
                if child.tag == 'notes-citeas':
                    self.process_citeas_notes(parent_akn, child, eId)
                elif child.tag == 'notes-history':
                    self.process_notes_history(comment_node, child)
                elif child.tag == 'notes-priorhistory':
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
                elif child.tag == 'notes-cn':    
                    self.process_notes_std(comment_node, child)
                elif child.tag == 'notes-auth':    
                    self.process_notes_std(comment_node, child)
                elif child.tag == 'notes-footnotes':    
                    self.process_notes_footnotes(comment_node, child)
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

    def process_citeas_notes(self, comment_node, node, eId):
        for child in node:
            if ET.iselement(child) and child.tag == 'note':
                self.process_citeas(comment_node, child, eId)
            else:
                self.logger.warning ('Ignored node in notes-citeas %s', ET.tostring(child))

    def remove_cntrl_chars(self, s):
        s, n = re.subn(r'[\x00-\x1f\x7f-\x9f\s]+', ' ', s)
        return s

    def process_citeas(self, comment_node, node, eId):
        text = ET.tostring(node, method = 'text', encoding = 'unicode')
        primaryid = node.find('primaryidcodenumber')

        if primaryid == None:
            primaryid = node.find('rulenumber')

        d = {}
        if primaryid != None:
            d['title'] = self.remove_cntrl_chars(primaryid.text)

        codesec = node.find('codesec')
        if codesec != None:
            d['num'] = codesec.text

        if eId:
            d['secid'] = eId

        citenode = create_node('neutralCitation', comment_node, d) 
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

 
    def process_codesec(self, parent_akn, node, state, title, catchline):
        if state in ['MI', 'GA', 'ID', 'LA', 'ME', 'MS', 'NE']:
            text = node.get('use')
        else:
            text = node.text

        if state in ['WI', 'SC', 'CO', 'DE']:
            text = node.get('use')
            if not text:
                text = node.text

        if state in ['MO']:
            text = self.remove_cntrl_chars(text)

        citenode = create_node('ref', parent_akn, {'href': ''})
        if text:
            citenode.attrib['use'] = text

        if state == 'NE' and text:    
            reobj = re.search('(?P<title>\d+)-(?P<num>.+)', text)
            if reobj:
                groupdict = reobj.groupdict()
                citenode.attrib['title'] = groupdict['title']
                citenode.attrib['use']   = groupdict['num']
        elif state in title_states and title and state not in ['WI']:
            citenode.attrib['title'] = title

        if state:
            citenode.attrib['state'] = state
        if catchline:
            citenode.attrib['catchline'] = catchline

        text = ET.tostring(node, method = 'text', encoding = 'unicode')
        citenode.text = text

    def process_codecitation(self, parent_akn, node):
        span_akn = create_node('span', parent_akn)

        datatype = node.get('datatype')
        state = node.get('statecd')
        title = node.get('title')
        catchline  = node.get('catchline')
        if datatype == 'D' and (state not in ['CA', 'PA', 'NY'] or title != None ) and state == self.statecd:
            self.copy_text(span_akn, node)

            for child in node:
                if ET.iselement(child):
                    if child.tag == 'codesec':
                        self.process_codesec(span_akn, child, state, title, catchline)
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

    def process_primaryid(self, parent_akn, node):
        anode = create_node('ref', parent_akn, {'href': ''})
        self.copy_text(anode, node)

    def get_akn_date(self, datestr):
        ds = re.findall('\d+', datestr)
        if len(ds) != 3:
            self.logger.warn('Not able to get date from %s', datestr)
            return None

        return '%s-%s-%s' % (ds[2], ds[0], ds[1])

    def process_date(self, parent_akn, node, datestr, refersTo):
        datenode = create_node('date', parent_akn, {'refersTo': refersTo})
        if datestr:
                datenode.set('date', datestr)
        self.copy_text(datenode, node)

    def process_regcitation(self, parent_akn, node):
        href = self.media_url + node.get('filename')
        anode = create_node('a', parent_akn, {'href': href})
        self.copy_text(anode, node)

    def process_strike(self, parent_akn, node):
        delnode = create_node('del', parent_akn)
        self.copy_text(delnode, node)

    def process_effective_date(self, parent_akn, node):
        d = node.get('use')
        if d == None:
            d = node.text
        datestr = self.get_akn_date(d)
        self.process_date(parent_akn, node, datestr, '#effectivedate')

    def process_one_reviewdate(self, parent_akn, node):
        d = node.get('use')
        if d == None:
            d = node.text
        datestr = self.get_akn_date(d)
        self.process_date(parent_akn, node, datestr, '#reviewdate')

    def process_expiration_date(self, parent_akn, node):
        d = node.get('use')
        if d == None:
            d = node.text
        datestr = self.get_akn_date(d)
        self.process_date(parent_akn, node, datestr, '#expirationdate')

    def process_operational_date(self, parent_akn, node):
        d = node.get('use')
        if d == None:
            d = node.text
        datestr = self.get_akn_date(d)
        self.process_date(parent_akn, node, datestr, '#operationaldate')

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
                    self.process_effective_date(comment_node, child)
                elif child.tag == 'operationaldate':
                    self.process_operational_date(comment_node, child)
                elif child.tag == 'regcitation':
                     self.process_regcitation(comment_node, child)
                elif child.tag == 'linebreak':
                     create_node('br', comment_node)
                elif child.tag == 'subscript':
                    self.process_subscript(comment_node, child)
                elif child.tag == 'notetext':    
                    self.process_para(comment_node, child)
                elif child.tag == 'bold':
                    self.process_bold(comment_node, child)
                elif child.tag == 'filedate':
                    span_node = create_node('span', comment_node)
                    self.copy_text(span_node, child)
                elif child.tag == 'ordercitation':
                    self.process_filelink(comment_node, child)
                elif child.tag == 'filelink':
                    self.process_filelink(comment_node, child)
                elif child.tag == 'drop':
                    self.process_drop(comment_node, child)
                elif child.tag == 'expirationdate':
                    self.process_expiration_date(comment_node, child)
                elif child.tag == 'primaryidcodenumber':
                    self.process_primaryid(comment_node, child)
                elif child.tag == 'codesec':
                    self.copy_text_nonempty(comment_node, child)
                elif child.tag == 'reviewdate':
                    self.process_one_reviewdate(comment_node, child)
                elif child.tag == 'reviewdates':
                    self.process_reviewdates(comment_node, child)
                elif child.tag == 'ulink':
                    self.process_ulink(comment_node, child)
                elif child.tag == 'underscore':
                    self.process_underscore(comment_node, child)
                elif child.tag == 'superscript':
                    self.process_superscript(comment_node, child)
                else:    
                    self.logger.warning ('Ignored element in note %s', ET.tostring(child))
            else:       
                 self.logger.warning ('Ignored node in note %s', child)

    def process_reviewdates(self, parent_akn, node):
        pnode = create_node('p', parent_akn)
        self.copy_text(pnode, node)

        for child in node:
            if ET.iselement(child):
                if child.tag == 'reviewdate':
                    self.process_one_reviewdate(pnode, child)
                elif child.tag == 'codecitation':
                    self.process_codecitation(pnode, child)

                else:    
                    self.logger.warning ('Ignored element in reviewdates %s', ET.tostring(child))
            else:       
                self.logger.warning ('Ignored node in reviewdates %s', child)

    def process_number(self, parent_akn, node):
        number_node = create_node('num', parent_akn)
        number_node.text = ET.tostring(node, method='text', encoding='unicode', with_tail=False)

    def process_heading(self, parent_akn, node, prefix = None):
        heading_node = create_node('heading', parent_akn)
        text = ET.tostring(node, method='text', encoding='unicode', with_tail=False)
        if prefix:
            heading_node.text = prefix + ' - ' + text
        else:    
            heading_node.text = text

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
                    if regulation:
                        regulation.set_publish_date(child.text) 
                elif child.tag == 'codetext':    
                    self.process_codetext(content_akn, child, section_akn, section_eid)
                elif child.tag == 'number':    
                   self.process_number(content_akn, child)
                elif child.tag == 'notes':
                    self.process_notes(content_akn, child, section_eid, regulation)
                elif child.tag == 'subsect':
                    subsection_eid = '%s__subsec_%d' % (eId, subsection)
                    subsection += 1
                    self.process_subsection(section_akn, child, subsection_eid, regulation)
                elif child.tag == 'version':
                    pass
                elif child.tag == 'name':
                   self.process_heading(hcontent_akn, child)
                elif child.tag == 'content':
                   content += 1
                   subcontent_eid = '%s_content_%d' % (eId, content)
                   self.process_content(section_akn, child, subcontent_eid, section_eid, regulation)
                elif child.tag == 'code' and child.get('type') == 'Section':
                   self.process_section(hcontent_akn, child, regulation)
                elif child.tag == 'code' and child.get('type') in ['Exhibit', 'Appendix']:
                    self.process_group(hcontent_akn, child, regulation)
                else:    
                    self.logger.warning ('Ignored element in content %s', ET.tostring(child))
            else:       
                self.logger.warning ('Ignored node in content %s', child)
                    
    def process_table_content(self, parent_akn, node):
        content_akn  = create_node('content', parent_akn)

        for child in node:
            if ET.iselement(child):
                if child.tag == 'currency':
                    comment_node = self.add_comment_node(content_akn)
                    comment_node.text = child.text
                elif child.tag == 'notes':
                    self.process_notes(content_akn, child, None, None)
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
                elif child.tag == 'TABLE':
                    self.process_table(parent_akn, child)
                elif child.tag == 'literallayout':
                    self.process_pre(parent_akn, child)
                elif child.tag == 'itemizedlist':
                    self.process_list(parent_akn, child)
                elif child.tag == 'nbsp':
                    self.process_nbsp(parent_akn, child)
                elif child.tag == 'strike':
                    self.process_strike(parent_akn, child)
                elif child.tag == 'filelink':
                    self.process_filelink(parent_akn, child)
                elif child.tag == 'bold':
                    self.process_bold(parent_akn, child)
                elif child.tag == 'italic':
                    self.process_italic(parent_akn, child)
                elif child.tag == 'codecitation':
                    self.process_codecitation(parent_akn, child)
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
                elif child.tag == 'code' and child.get('type') == 'Article':
                   self.process_article(parent_akn, child, regulation)
                elif child.tag == 'code' and child.get('type') == 'Section':
                   self.process_section(article_akn, child, regulation)
                elif child.tag == 'code' and child.get('type') == 'Sec2':
                   self.process_section(article_akn, child, regulation)
                elif child.tag == 'code' and child.get('type') == 'Undesignated':
                   self.process_group(article_akn, child, regulation)
                elif child.tag == 'code' and child.get('type') == 'Appendix':
                    self.process_appendix(article_akn, child, regulation)
                elif child.tag == 'code' and child.get('type') == 'Table':
                    self.process_group(article_akn, child, regulation)
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
                    self.process_notes(article_akn, child, eId, regulation)
                elif child.tag == 'table' or child.tag == 'TABLE':
                    self.process_table(article_akn, child)
                elif child.tag == 'code' and child.get('type') == 'Subchapter':
                    subchap_eId = '%s_subchap_%d' % (eId, subchap)
                    subchap += 1
                    self.process_subchapter(article_akn, child, regulation, subchap_eId)
                elif child.tag == 'code' and child.get('type') == 'Chapter':    
                    self.process_chapter(article_akn, child, regulation)
                elif child.tag == 'code' and child.get('type') == 'Rule':
                    self.process_section(article_akn, child, regulation)
                elif child.tag == 'code' and child.get('type') in ['Exhibit', 'Form', 'Attachment', 'Schedule']:
                    self.process_group(article_akn, child, regulation)
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
                   self.process_group(content_akn, child, regulation)
                elif child.tag == 'code' and child.get('type') == 'Appendix':
                    self.process_appendix(content_akn, child, regulation)
                elif child.tag == 'code' and child.get('type') == 'Subarticle':
                    self.process_subarticle(content_akn, child, regulation)
                elif child.tag == 'code' and child.get('type') == 'Part':
                    self.process_part(content_akn, child, regulation)
                elif child.tag == 'code' or child.get('type') == 'Table':
                    self.process_group(content_akn, child, regulation)
                elif child.tag == 'table' or child.tag == 'TABLE':
                    self.process_table(content_akn, child)
                elif child.tag == 'content':
                   content_eid = '%s__hcontainer_%d' % (eId, content_num)
                   self.process_content(content_akn, child, content_eid, eId, regulation)
                   content_num += 1
                elif child.tag == 'version':
                   # no idea what to do about the version tag
                   pass
                elif child.tag == 'notes':
                    self.process_notes(content_akn, child, eId, regulation)
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
                if child.tag == 'subsect' or \
                       (child.tag == 'code' and \
                        child.get('type') in ['Subsection', 'Rule', 'Section', 'Unprefixed', 'Part', 'Article']):  
                   subsection_eid = '%s__subsec_%d' % (eId, subsection)
                   subsection += 1
                   self.process_subsection(section_akn, child, subsection_eid, regulation)
                elif child.tag == 'code' and child.get('type') == 'Undesignated':
                   self.process_part(parent_akn, child, regulation)
                elif child.tag == 'number':
                   self.process_number(section_akn, child)
                   regulation.set_num(child.text)
                elif child.tag == 'name':
                   self.process_heading(section_akn, child)
                elif child.tag == 'content' or (child.tag == 'code' and child.get('type')=='Exhibit'):
                   content_eid = '%s__hcontainer_%d' % (eId, content_num)
                   self.process_content(section_akn, child, content_eid, eId, regulation)
                   content_num += 1
                elif child.tag == 'version':
                   version_node = create_node('version', section_akn)
                   version_node.text = child.text
                elif child.tag == 'notes':
                    self.process_notes(section_akn, child, eId, regulation)
                elif child.tag == 'code' and child.get('type')=='Appendix':
                    self.process_appendix(section_akn, child, regulation)
                elif child.tag == 'code' and child.get('type')  in ['Form', 'Attachment', 'Schedule', 'Table', 'Sec2', 'Rule2', 'Subpart']:
                    self.process_group(section_akn, child, regulation)
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

    def process_subsection(self, section_akn, node, eId, regulation = None):
        subsection_akn = create_node('subsection', section_akn)
        if eId:
            node.set('eId', eId)
        content_akn    = None
        subsection     = 1
        para_node      = None
        content_num    = 1
        num            = None
        for child in node:
            if ET.iselement(child):
                if child.tag in ['designator', 'number']:
                    self.process_number(subsection_akn, child)
                    num = ET.tostring(child, method='text', encoding='unicode', with_tail=False)
                    content_akn = create_node('content', subsection_akn)
                    para_node = create_node('p', content_akn)
                    if child.tail:
                        para_node.text = child.tail
                elif child.tag == 'subsect' or (child.tag == 'code' and child.get('type') in ['Rule', 'Section']):
                    subsection_eid = '%s__subsec_%d' % (eId, subsection)
                    subsection += 1
                    self.process_subsection(subsection_akn, child, subsection_eid, regulation)
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
                elif child.tag == 'literallayout':
                    self.process_pre(para_node, child)
                elif child.tag == 'version': 
                    pass
                elif child.tag == 'name':
                    self.process_heading(subsection_akn, child)
                elif child.tag == 'content':    
                    content_eid = '%s__hcontainer_%d' % (eId, content_num)
                    content_num += 1
                    self.process_content(subsection_akn, child, content_eid, eId, None)
                elif child.tag == 'add':    
                    self.process_add(subsection_akn, child, eId)
                elif child.tag == 'itemizedlist':    
                    self.process_list(subsection_akn, child)
                elif child.tag == 'footnoteref':
                    self.process_footnoteref(subsection_akn, child)
                elif child.tag == 'nbsp':
                    self.process_nbsp(para_node, child)
                elif child.tag == 'del':
                    self.process_strike(para_node, child)
                elif child.tag == 'filelink':
                    self.process_filelink(para_node, child)
                elif child.tag == 'effectivedate':
                    self.process_effective_date(para_node, child)
                #elif child.tag == 'code' and child.get('type') == 'Section':
                #    self.process_section(section_akn, child, regulation)
                elif child.tag == 'code' and child.get('type') == 'Appendix':
                     self.process_appendix(subsection_akn, child, regulation)
                elif child.tag == 'code' and child.get('type') in ['Exhibit']:
                    self.process_group(subsection_akn, child, regulation)
                else:    
                    self.logger.warning ('Ignored element in subsection %s %s', num, ET.tostring(child))
                if child.tag not in ['designator', 'subsect', 'codecitation', 'para', 'ulink', 'actcitation', 'superscript', 'subscript', 'bold', 'underscore', 'italic', 'strike', 'content', 'name', 'number', 'code', 'literallayout', 'add', 'itemizedlist', 'footnoteref', 'nbsp', 'del', 'filelink', 'effectivedate']:
                    if para_node == None:
                        print ('Unknown subsection child', child.tag)
                        #print (ET.tostring(node))

                    if child.text:
                        self.add_text(para_node, child)

                    if child.tail:
                        self.add_tail(para_node, child)
            else:       
                self.logger.warning ('Ignored node in subsection %s', child)

    def process_add(self, parent_akn, node, eId):
        comment_node = create_node('remark', parent_akn, \
                                   {'status': 'editorial'})
        comment_node.text = 'Added in sessionyear %s' % node.get('sessionyear')

        subsection = 1
        for child in node:
            if ET.iselement(child):
                if child.tag == 'subsect':
                    subsection_eid = '%s__subsec_%d' % (eId, subsection)
                    subsection += 1
                    self.process_subsection(parent_akn, child, subsection_eid)
                elif child.tag == 'codecitation':
                    self.process_codecitation(parent_akn, child)
                elif child.tag == 'strike':
                    self.process_strike(parent_akn, child)
                elif child.tag == 'add':    
                    self.process_add(parent_akn, child, eId)
                elif child.tag == 'actcitation':
                    self.process_actcitation(parent_akn, child)
                elif child.tag == 'bold':
                    self.process_bold(parent_akn, child)
                elif child.tag == 'italic':
                    self.process_italic(parent_akn, child)
                elif child.tag == 'superscript':
                    self.process_superscript(parent_akn, child)
                elif child.tag == 'subscript':
                    self.process_subscript(parent_akn, child)
            else:       
                self.logger.warning ('Ignored node in add %s', child)

        
    def process_pre(self, parent_akn, node):
        text = ET.tostring(node, method = 'text', encoding = 'unicode')

        txtlines = text.splitlines()
        for txt in txtlines:
            p = create_node('p', parent_akn)
            p.text = txt

    def process_list(self, parent_akn, node):
        list_node = create_node('blockList', parent_akn)
        for child in node:
            if child.tag == 'listitem':
                self.process_item(list_node, child)
            else:       
                self.logger.warning ('Ignored node in list %s', child)

    def process_item(self, parent_akn, node):
        item_akn = create_node('item', parent_akn)
        self.process_para(item_akn, node)

    def process_monospace(self, parent_akn, node):
        self.copy_text(parent_akn, node)

    def process_footnoteref(self, parent_akn, node):
        href = node.get('linkend')
        if not href:
            self.logger.warning('No link in %s', ET.tostring(node))

        refnode = create_node('ref', parent_akn, {'href': '#%s' % href})
        self.copy_text(refnode, node)

    def process_notes_footnotes(self, parent_akn, node):        
        for child in node:
            if child.tag == 'note':
                self.process_footnote(parent_akn, child)
            else:
                self.logger.warning ('Ignored node in notes-footnotes %s', child)

    def process_footnote(self, parent_akn, node):
        eId = node.get('id')
        note_akn = create_node('note', parent_akn, {'eId': eId})
        for child in node:
            if child.tag == 'para':
                 self.process_para(note_akn, child)
            else:     
                self.logger.warning ('Ignored node in footnote %s', child)
                
    def process_drop(self, parent_akn, node):
        self.copy_text_nonempty(parent_akn, node)
        
    def copy_text_nonempty(self, parent_akn, node):
        if node.text:
            if parent_akn.text:
                parent_akn.text += node.text
            else:    
                parent_akn.text = node.text
                
        if node.tail:
            if parent_akn.text:
                parent_akn.text += node.tail
            else:    
                parent_akn.text = node.tail
