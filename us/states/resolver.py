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
            t = refids[num]
            if t[0] == uri and t[1] == eid:
                return

            oldver = refids[num][2]
            if oldver != None and version!= None and version <= oldver:
                self.logger.warning('Refid already exists %s %s %s for (%s, %s, %s)', regs_title, num, refids[num], uri, eid, version)
                return
            else:
                self.logger.warning('Refid replacement of %s %s %s with (%s, %s, %s)', regs_title, num, refids[num], uri, eid, version)
                
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
        if regulation.statecd in ['CA', 'PA', 'NY', 'IL', 'NC']:
            num = regulation.get_num()
            if not num:
                self.logger.warning ('RefResolver: NO NUM %s', regulation)
                return

            regs_title = num
        self.add_sections(regulation.body_akn, uri, regs_title)

    def add_sections(self, akn, uri, regs_title):    
        for node in akn.iter('section'):
            self.add_num(node, uri, regs_title)

        for node in akn.iter('neutralCitation'):
            regs_title = node.get('title')

            eId = node.get('secid')
            if eId:
                num = node.get('num')
                self.add_refid(num, uri, eId, None, regs_title)

    def add_num(self, node, uri, regs_title, num = None):
        if num == None:
            numnode = node.find('num')
            if numnode == None:
                return 
            num =  numnode.text

        version = node.find('version')
        if version != None:
            version = int(version.text)

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
        statecd = regulation.statecd

        success = 0
        failure = 0
        for node in regulation.body_akn.iter('ref'):
            text = node.get('use')
            title = node.get('title')
            stateref = node.get('state')
            if stateref != statecd:
                self.logger.warning('Outside state ref. Ignoring %s', ET.tostring(node), reguri)
                continue

            if not text:
                text = node.text

            if not text:
                self.logger.warning('Nothing to resolve here %s %s', ET.tostring(node), reguri)
                continue

            if not title:
                title = regulation.get_num()

            d  = self.resolve_num(title, text)
            uri, eId, version = d 
            if uri == None:
                failure += 1
                self.logger.warning('Could not resolve %s %s', ET.tostring(node), reguri)
                continue

            success += 1
            if uri == reguri:
                href = '#%s' % eId
            else:
                href = '%s#%s' % (uri, eId)

            node.attrib['href'] = href
        self.logger.warn('Successfully resolved %d. Failed in %d for %s', success, failure, regulation.get_num()) 
