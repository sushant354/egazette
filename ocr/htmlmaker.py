import cgi

from egazette.ocr.annotations import Node, annotate_doc

class HtmlMaker:
    def __init__(self):
        self.htmlroot = Node(0, None, 'html', None, None)
        self.current_node = self.htmlroot
        self.pos  = 0
        self.text = []

    def process_page(self, response):
        for page in response.full_text_annotation.pages:
            ordered_blocks = self.order_blocks(page.blocks, page.width, \
                                               page.height)  
            
            for category, block in ordered_blocks:
                self.process_block(category, block)

    def classify_block(self, block, width, height):
        left  = (block.bounding_box.vertices[0].x * 100/width)
        right = (block.bounding_box.vertices[1].x * 100/width)
        top   = (block.bounding_box.vertices[0].y * 100/height)
        bottom = (block.bounding_box.vertices[2].y * 100/height)

        print (left, right, top, bottom)
        if top >= 90:
            return 'footnote', 'footnote'
        if abs(left + right - 100) <= 10 and left > 25:
            return '1st', 'center'

        if right <= 55:
            return '1st', 'left_column'

        if left >= 45:    
            return '2nd', 'right_column'
        return '1st', 'left_column'

    def order_blocks(self, blocks, width, height):
        blockdict = {}
        for block in blocks:
             order, category = self.classify_block(block, width, height)
             print (order, category, block.bounding_box)
             if order not in blockdict:
                 blockdict[order] = []
             blockdict[order].append((category, block)) 


        ordered_blocks = []
        for order in ['1st', '2nd', '3rd']:
            if order in blockdict:
                col = blockdict[order]
                col.sort(key = lambda x: x[1].bounding_box.vertices[0].y)
                ordered_blocks.extend(col)

        return ordered_blocks    

    def process_block(self, category, block):
        if category == 'center':
            center_node = Node(self.pos, None, 'center', self.current_node, None)
            self.current_node.add_child(center_node)
            self.current_node = center_node

        for para in block.paragraphs:
            self.process_para(para.words)

        if category == 'center':
            center_node.end = self.pos
            self.current_node = center_node.parent
    
    def process_para(self, words):
        para_node = Node(self.pos, None, 'p', self.current_node, None)
        self.current_node.add_child(para_node)

        wordlist = []
        for word in words:
            stext = []
            for symbol in word.symbols:
                if symbol.text:
                    stext.append(symbol.text)

                if hasattr(symbol.property, 'detected_break'):
                    t = symbol.property.detected_break.type
                    if t == 1 or t == 3:
                        stext.append(' ')
                    elif t == 5:
                        stext.append('\n')
            wordlist.append(''.join(stext))

        para_text = ''.join(wordlist)

        self.text.append(para_text)
        self.pos += len(para_text)
        para_node.end = self.pos

    def get_annotated_doc(self):
        current_node = self.current_node
        while current_node != None:
            current_node.end = self.pos
            current_node = current_node.parent

        doc = ''.join(self.text)
        doc, segmentmap =  annotate_doc(doc, [self.htmlroot])
        doc = '<!DOCTYPE HTML>\n' + doc
        return doc
