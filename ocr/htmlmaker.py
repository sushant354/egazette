import cgi
import re

from egazette.ocr.annotations import Node, annotate_doc

class Vertex:
    def __init__(self, vertex):
        self.x = vertex.x
        self.y = vertex.y

class BoundingBox:
    def __init__(self):
        self.vertices = None
    
    def __repr__(self):
        x = 'vertices{\n\tx: %d\n\ty: %d\n}\n'
        s = []
        for v in self.vertices:
           s.append(x % (v.x, v.y))
        return ''.join(s) 

    def update(self, word):
        vs = word.bounding_box.vertices
        if not self.vertices:
            self.vertices = (Vertex(vs[0]), Vertex(vs[1]), \
                             Vertex(vs[2]), Vertex(vs[3]))
            return

        if vs[0].x < self.vertices[0].x:
           self.vertices[0].x = vs[0].x

        if vs[0].y < self.vertices[0].y:
           self.vertices[0].y = vs[0].y

        if vs[1].x > self.vertices[1].x:
           self.vertices[1].x = vs[1].x

        if vs[1].y < self.vertices[1].y:
           self.vertices[1].y = vs[1].y

        if vs[2].x > self.vertices[2].x:
           self.vertices[2].x = vs[2].x

        if vs[2].y > self.vertices[2].y:
           self.vertices[2].y = vs[2].y

        if vs[3].x < self.vertices[3].x:
           self.vertices[3].x = vs[3].x

        if vs[3].y > self.vertices[3].y:
           self.vertices[3].y = vs[3].y

class Paragraph:
    def __init__(self):
        self.words = []

    def add_word(self, word):
        self.words.append(word)

class PageBlock:
    def __init__(self):
        self.bounding_box = BoundingBox()
        self.paragraphs   = []
        self.current      = -1

        
    def add_word(self, word, newpara):
        if newpara:
            self.paragraphs.append(Paragraph())
            self.current += 1
        self.paragraphs[self.current].add_word(word)

        self.bounding_box.update(word)

    def add_para(self, para):
        newpara = True
        for word in para.words:
            self.add_word(word, newpara)
            newpara = False

class LineWords:
    def __init__(self):
        self.words = []

    def add_word(self, word):
        self.words.append(word)

    def get_width(self):
        if not self.words:
            return 0

        return self.words[-1].bounding_box.vertices[1].x - self.words[0].bounding_box.vertices[0].x   

    def get_start(self):
        if not self.words:
            return -1
        return self.words[0].bounding_box.vertices[0].x     

    def get_end(self):    
        if not self.words:
            return -1
        return self.words[-1].bounding_box.vertices[1].x     

    def get_height(self):
        if not self.words:
            return -1

        ht = 0.0
        for word in self.words:
           word_ht = word.bounding_box.vertices[3].y - word.bounding_box.vertices[0].y
           if word_ht > ht:
               ht = word_ht
        return ht

    def get_top_offset(self):
        y = -1
        for word in self.words:
            y1 = word.bounding_box.vertices[0].y
            if y < 0 or y > y1:
                y = y1
        return y


class HtmlMaker:
    def __init__(self):
        self.htmlroot = Node(0, None, 'html', None, None)
        self.current_node = self.htmlroot
        self.pos  = 0
        self.text = []
        self.abbreviation_re = re.compile(' (A\.D|a\.m|C\>?V|e\.?g|et al|etc|i\.e|p.a|p\.?m|P\.?S|Dr|Gen|Hon|Mr|Mrs|Ms|Prof|Rev|Sr|Jr|St|Assn|Ave|Dept|est|Fig|fig|hrs|Inc|Mt|No|oz|sq|st|vs|Vs|Sri|Shri|Smt)\.$')

    def process_page(self, response):
        for page in response.full_text_annotation.pages:
            width  = page.width
            height = page.height


            blocks = self.fix_incorrect_blocks(page.blocks, width, height)
            ordered_blocks = self.order_blocks(blocks, width, height)  
            
            for category, block in ordered_blocks:
                self.process_block(category, block)
  
    def is_past_halfway(self, word, width):
        return word.bounding_box.vertices[0].x > width/2

    def is_new_line(self, prev_word, word):
        return word.bounding_box.vertices[0].x < prev_word.bounding_box.vertices[0].x 

    def get_word_gap(self, prev_word, word):
        return word.bounding_box.vertices[0].x - prev_word.bounding_box.vertices[1].x 

    def is_twoline(self, lines, width):
        if len(lines) == 2 and len(lines[0].words) > 0 and len(lines[1].words) > 0:
            word1 = lines[0].words[0]
            word2 = lines[1].words[0]
            if self.is_past_halfway(word1, width) and not self.is_past_halfway(word2, width):
                return True
        return False

    def is_para_twocol(self, para, width):
        lines = self.get_lines(para)
        if self.is_twoline(lines, width):
            return True

        count     = 0 
        word_gap  = 0
        for linewords in lines:
            prev_word = 0
            for word in linewords.words:
                if prev_word:
                    word_gap += self.get_word_gap(prev_word, word)
                    count += 1
                prev_word = word

        if count <= 0:
            return False

        avg_word_gap = word_gap /count

        prev_word = None
        twocol    = False
        for linewords in lines:
            prev_word = 0
            for word in linewords.words:
               #if prev_word: 
                   #print (self.get_word_text(prev_word), self.get_word_text(word), width, self.get_word_gap(prev_word, word), word.bounding_box.vertices[0].x, prev_word.bounding_box.vertices[0].x)
                if prev_word and not self.is_past_halfway(prev_word, width) and\
                        self.is_past_halfway(word, width):
                    word_gap = self.get_word_gap(prev_word, word)
                    #print ('GAP', word_gap, avg_word_gap, self.get_word_text(prev_word), self.get_word_text(word))
                    if word_gap > 2.5* avg_word_gap:
                        twocol = True
                    else:
                        twocol = False
                        break
            
                prev_word = word
        #print ('TWOCOL', twocol)   
        #print ('PARATEXT', self.get_para_text(para.words))
        return twocol

    def print_block(self, block):
        print ('----------------------------------------------------------------')
        for para in block.paragraphs:
            print ('PARATEXT', self.get_para_text(para.words))

    def is_block_twocol(self, block, width):
        num = 0
        for para in block.paragraphs:
            if self.is_para_twocol(para, width):
                num += 1
        return num > 0.67 * len(block.paragraphs)

    def is_sentence_end(self, para_text):
        para_text = para_text.strip()
        last = para_text[-1]
        if last == '.' and self.abbreviation_re.search(para_text) == None or\
               last == '\u0964':
            return True
        return False

    def split_twocol(self, block, width):
        left_block   = PageBlock()
        right_block  = PageBlock()

        left_para  = True
        right_para = True
        for para in block.paragraphs:

            for word in para.words:
                if self.is_past_halfway(word, width): 
                    right_block.add_word(word, right_para)
                    right_para = False
                else:
                    left_block.add_word(word, left_para)
                    left_para = False
            if right_block.current >= 0:        
                para_text = self.get_para_text(right_block.paragraphs[right_block.current].words)
                if para_text and self.is_sentence_end(para_text):
                    right_para = True
            #print ('RIGHT', para_text, right_para)

            if left_block.current >= 0:        
                para_text = self.get_para_text(left_block.paragraphs[left_block.current].words)
                if para_text and self.is_sentence_end(para_text):
                    left_para = True
           # print ('LEFT', para_text, left_para)
                

        return [left_block, right_block] 

    def fix_incorrect_blocks(self, blocks, width, height):
        new_blocks = []
        for block in blocks:
            if self.is_block_twocol(block, width):
                split_blocks = self.split_twocol(block, width)
                new_blocks.extend(split_blocks)
            else:
                new_blocks.append(block)
        return new_blocks

    def classify_block(self, block, width, height):
        left  = (block.bounding_box.vertices[0].x * 100/width)
        right = (block.bounding_box.vertices[1].x * 100/width)
        top   = (block.bounding_box.vertices[0].y * 100/height)
        bottom = (block.bounding_box.vertices[2].y * 100/height)

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

    def get_lines(self, para):
        prev_word = None
        linewords = LineWords()
        lines     = [linewords]
        for word in para.words:
            if prev_word and self.is_new_line(prev_word, word):
                linewords = LineWords()
                lines.append(linewords)
            linewords.add_word(word)
            prev_word = word

        return lines

    def split_paras(self, lines):
        paragraph = Paragraph()
        new_paras = [paragraph]   
        prev_line = None
        for linewords in lines:
           is_new_para = False
           start_pos = linewords.get_start() 
           end_pos   = linewords.get_end()
           width     = linewords.get_width()

           if prev_line and self.is_sentence_end(self.get_para_text(prev_line.words)):
               h1 = linewords.get_top_offset()
               h2 = prev_line.get_top_offset()
               ht_diff = (h1-h2)

               #print (ht_diff, linewords.get_height(), ht_diff*1.0/ linewords.get_height(), self.get_para_text(linewords.words))
               if ht_diff > 1.3 * linewords.get_height():
                   is_new_para = True
           line_text = self.get_para_text(linewords.words)
           line_text = line_text.strip()
           if re.match('\w\)\s+', line_text) or re.match('[\d\sA-Z]+$', line_text):
               is_new_para = True

           if is_new_para:       
               paragraph = Paragraph()
               new_paras.append(paragraph)

           for word in linewords.words:
               paragraph.add_word(word)
           prev_line = linewords 

        return new_paras

    def process_lines(self, lines):
        new_paras = self.split_paras(lines)
        for p in new_paras:
            self.process_para(p.words)

    def process_block(self, category, block):
        if category == 'center':
            center_node = Node(self.pos, None, 'center', self.current_node, None)
            self.current_node.add_child(center_node)
            self.current_node = center_node

        lines = []    
        for para in block.paragraphs:
            para_text = self.get_para_text(para.words)
            new_lines = self.get_lines(para)
            if self.is_sentence_end(para_text):
                if lines:
                    self.process_lines(lines)
                lines = []    
            lines.extend(new_lines)

        if lines:
            self.process_lines(lines)

        if category == 'center':
            center_node.end = self.pos
            self.current_node = center_node.parent

    def get_word_text(self, word):
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
        return ''.join(stext)

    def get_para_text(self, words):
        wordlist = []
        for word in words:
            word_text = self.get_word_text(word)
            wordlist.append(word_text)

        para_text = ''.join(wordlist)
        return para_text

    def process_para(self, words):
        para_node = Node(self.pos, None, 'p', self.current_node, None)
        self.current_node.add_child(para_node)

        para_text  = self.get_para_text(words)
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
