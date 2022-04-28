import logging
import lxml.etree as ET

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
 
