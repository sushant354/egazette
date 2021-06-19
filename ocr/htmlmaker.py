import cgi
import re

from egazette.ocr.annotations import Node, annotate_doc
from egazette.ocr.textmaker import TextMaker

from egazette.ocr.gapi import Paragraph, PageBlock, LineWords 

class HtmlMaker:
    def __init__(self):
        self.htmlroot = Node(0, None, 'body', None, None)
        self.current_node = self.htmlroot
        self.pos  = 0
        self.text = []
        self.textmaker = TextMaker()
        self.abbreviation_re = re.compile(' (A\.D|a\.m|C\>?V|e\.?g|et al|etc|i\.e|p.a|p\.?m|P\.?S|Dr|Gen|Hon|Mr|Mrs|Ms|Prof|Rev|Sr|Jr|St|Assn|Ave|Dept|est|Fig|fig|hrs|Inc|Mt|No|oz|sq|st|vs|Vs|Sri|Shri|Smt|etc)\.$')
        self.pagenum  = 0

    def is_pre(self, page):
        numwords = 0
        numpara  = 0
        for block in page.blocks:
            numpara += len(block.paragraphs)
            for para in block.paragraphs:
                numwords += len(para.words)
        pre = False
        per_para = numwords/numpara

        #if numwords < 600:
        #    print (self.pagenum + 1, numwords, per_para)
        if numwords < 600 and per_para < 20:
           pre = True
        return pre

    def process_page(self, response):
        for page in response.full_text_annotation.pages:
            self.footnotes = []
            if self.is_pre(page):
                self.process_pre(page)
            else:    
                self.process_txt(page)

            for footnote in self.footnotes:
                self.process_footnote(footnote.words)

            self.add_page_end()

    def process_txt(self, page):
        width  = page.width
        height = page.height

        blocks = self.fix_incorrect_blocks(page.blocks, width, height)
        ordered_blocks = self.order_blocks(blocks, width, height)  
            
        for category, block in ordered_blocks:
            self.process_block(category, block, height)
  
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
            if not twocol:
                break
        return twocol

    def print_block(self, block):
        print ('----------------------------------------------------------------')
        #vertices = block.bounding_box.vertices
        #print ('x1: ', vertices[0].x, 'x2:', vertices[1].x, 'y1:', vertices[1].y, 'y2:', vertices[2].y)
        for para in block.paragraphs:
            print ('PARATEXT', self.get_para_text(para.words))

    def is_block_twocol(self, block, width):
        num = 0
        for para in block.paragraphs:
            twocol = self.is_para_twocol(para, width)
            #print ('TWOCOL', twocol)   
            #print ('PARATEXT', self.get_para_text(para.words))
            if twocol:
                num += 1
        #print ('BLOCK', num, len(block.paragraphs))        
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

        #if top >= 90:
        #    return 'footnote', 'footnote'
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


    def split_paras(self, lines, width):
        paragraph    = Paragraph()
        new_paras    = [paragraph]   
        prev_line    = None
        last_allcaps = False
        last_width   = None

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
                   last_allcaps = False
                   #print ('PREV HT - NEW PARA', self.get_para_text(linewords.words))
                   is_new_para = True
           if  self.textmaker.is_all_capstart(linewords.words):
               if not last_allcaps:
                   is_new_para = True
               last_allcaps = True
           else:
               last_allcaps = False 
               

           line_text = self.get_para_text(linewords.words)
           line_text = line_text.strip()

           if re.match('\w\)\s+', line_text) or \
                   re.match('[\d\sA-Z]+$', line_text):
               is_new_para = True
           elif prev_line and re.match('[A-Z]', line_text):
               h1 = linewords.get_top_offset()
               h2 = prev_line.get_top_offset()
               ht_diff = (h1-h2)
               #print (ht_diff * 100/linewords.get_height(), line_text)
               if ht_diff > 1.3 * linewords.get_height():
                   is_new_para = True

           if is_new_para:       
               paragraph = Paragraph()
               new_paras.append(paragraph)

           for word in linewords.words:
               paragraph.add_word(word)
           prev_line = linewords 
           last_width = width

        return new_paras

    def is_footnote(self, line1, line2, page_ht):
        h1 = self.textmaker.get_top_offset(line1)
        h2 = self.textmaker.get_top_offset(line2)
        ht_diff = (h2-h1)
        ht      = self.textmaker.get_line_ht(line1)

        footnote = False
        if h2 > 0.85 * page_ht and ht_diff > 1.35 * ht:
            #print (ht_diff, ht, ht_diff * 1.0/ht)
            footnote = True

        return footnote

    def process_lines(self, lines, page_ht, width):
        if len(lines) == 1 and self.textmaker.get_top_offset(lines[0]) > 0.87* page_ht:
            #print ('SINGLE', self.textmaker.get_top_offset(lines[0]) * 1.0/page_ht)
            self.footnotes.append(lines[0])
            lines = []

        elif len(lines) > 1 and self.is_footnote(lines[-2], lines[-1], page_ht):
            self.footnotes.append(lines[-1])
            lines = lines[:-1]

        new_paras = self.split_paras(lines, width)
        for p in new_paras:
            if p.words:
                self.process_para(p.words)


    def process_block(self, category, block, page_ht):
        if category == 'center':
            center_node = Node(self.pos, None, 'center', self.current_node, None)
            self.current_node.add_child(center_node)
            self.current_node = center_node

        box   =  block.bounding_box
        width = box.vertices[1].x  - box.vertices[0].x 

        lines = []   
        for para in block.paragraphs:
            para_text = self.get_para_text(para.words)
            new_lines = self.get_lines(para)
            if self.is_sentence_end(para_text):
                if lines:
                    self.process_lines(lines, page_ht, width)
                lines = []    
            lines.extend(new_lines)

        if lines:
            self.process_lines(lines, page_ht, width)

        if category == 'center':
            center_node.end = self.pos
            self.current_node = center_node.parent

    def get_word_text(self, word):
        stext = []
        for symbol in word.symbols:
            if symbol.text:
                stext.append(symbol.text)

            if hasattr(symbol.property, 'detected_break'):
                t = symbol.property.detected_break.type_
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

    def process_pre(self, page):
        txtlines, footnotes = self.textmaker.get_pre_text(page)
        if footnotes:
            self.footnotes.extend(footnotes)

        self.pretext_to_html(txtlines)

    def get_min(self, lengths):
        count = {}
        for l in lengths:
            if l not in count:
               count[l] = 0
            count[l] += 1
        ls = list(count.keys())
        ls.sort(key = lambda x: count[x])
        return ls[0]

    def get_table_markers(self, spaces, maxlen):
        count = {}
        spaces.sort(key = lambda x: x[0])
        ldict = {}
        for pos, length in spaces:
            endpos = pos + length
            if endpos in count:
            
                count[endpos] += 1
            else:
                count[endpos] = 1
            if endpos in ldict:
                ldict[endpos].append(length)
            else:
                ldict[endpos] = [length]

        tdpos = []
        lastpos = None

        positions = list(count.keys())
        positions.sort()
        for pos in positions:
            length = self.get_min(ldict[pos])
            endpos = pos
            pos = pos - length

            if lastpos != None and pos < lastpos:
                continue

            if pos == 0 or count[pos+length] <=2:
                continue

            if endpos+ 1 in count and count[endpos] < count[endpos+1]:
                continue
              
            #if pos+2 in count and count[pos] < count[pos+2]:
            #    continue

            if  lastpos == None:
                td = [0, pos, count[endpos]]
            else:
                td = (lastpos, pos-lastpos, count[endpos])
            tdpos.append(td)
            lastpos = pos + length   

        if lastpos == None or lastpos < maxlen:
            if  lastpos == None:
                td = (0, maxlen, 1)
            else:
                td = (lastpos, maxlen - lastpos, 1)
            tdpos.append(td)
        return tdpos

    def pretext_to_html(self, txtlines):
        maxlen = 0
        spaces = []
        for line in txtlines:
            if not line.strip():
                continue
            if len(line) > maxlen:
                maxlen = len(line)

            ss = []    
            for reobj in re.finditer('\s+', line):
                length = reobj.end() - reobj.start()
                if length >= 2:
                    ss.append((reobj.start(), length))
            spaces.extend(ss)        
        tdpos = self.get_table_markers(spaces, maxlen)
        if len(tdpos) <= 1:
            for line in txtlines:
               para = Node(self.pos, None, 'p', self.current_node, None)
               self.current_node.add_child(para)
               self.text.append(line)
               self.pos += len(line)
               para.end = self.pos
        else:
             self.create_table(tdpos, txtlines)

    def create_table(self, tdpos, txtlines):         
        table_node = Node(self.pos, None, 'table', self.current_node, None) 
        self.current_node.add_child(table_node)

        for line in txtlines:
            if not line.strip(): # No need to create empty tr
                continue

            trnode = Node(self.pos, None, 'tr', table_node, None)
            table_node.add_child(trnode)

            start = 0    
            txts = []
            for reobj in re.finditer('\s+', line):
                if reobj.end() - reobj.start() < 2:
                    continue

                if reobj.start() > start:
                    txt = line[start:reobj.start()]
                    txts.append((start, txt))
                start = reobj.end()

            if start < len(line):
                txts.append((start, line[start:]))
             
            self.process_tds(trnode, txts, tdpos)
            trnode.end = self.pos

        table_node.end = self.pos

    def add_text(self, td, txt):
        if td[0]:
             td[0] = td[0] + ' ' + txt
        else:    
             td[0] = txt

    def process_tds(self, trnode, txts, tdpos):
        count = 0
        tds   = []
        lasttd = None

        consumed = [False for x in txts]
            
        for pos, length, num in tdpos:
            if count >= len(txts):
                tds.append(['', 1])
                lasttd = (pos, length, num)
                continue

            start, txt = txts[count]
            if start >= pos + length:
                tds.append(['', 1])
                lasttd = (pos, length, num)
                continue

            if start >= pos-1:
                tds.append([txt, 1])
                consumed[count] = True
                if start +len(txt) <= pos +length :
                    count += 1
            else:
                colspan = False
                if consumed[count]:
                    if start +len(txt) >= pos:
                        tds[-1][1]+=1
                        colspan = True
                    else:    
                        tds.append(['', 1])    
                elif lasttd:
                    if start - lasttd[0] - lasttd[1] < pos  - start - len(txt):
                       self.add_text(tds[-1], txt)
                       tds.append(['', 1])    
                    else:
                       tds.append([txt, 1])
                else:       
                    tds.append([txt, 1])

                consumed[count] = True
                if start + len(txt) > pos + length:
                    lasttd = (pos, length, num)
                    continue

                count += 1
                while count < len(txts):
                    start, txt = txts[count]
                    if start  > pos +length:
                        break
                    if colspan:
                        self.add_text(tds[-1], txt)
                    elif lasttd and start < pos -1 and \
                            start-lasttd[0]-lasttd[1] < pos-start-len(txt):
                        #print ('TD', tds[-2])    
                        self.add_text(tds[-2], txt)
                    else:
                        self.add_text(tds[-1], txt)
                    consumed[count] = True    
                    count += 1

            lasttd = (pos, length, num)

        for td in tds:
            txt = td[0]
            col = td[1]
            if col == 1:
                attrs = None
            else:
                attrs = [('colspan', col)]
            tdnode = Node(self.pos, None, 'td', trnode, attrs)
            self.text.append(txt)
            self.pos += len(txt)
            tdnode.end = self.pos
            trnode.add_child(tdnode)

    def get_tagname(self, para_text, words):
        if len(words) >= 6:
           tagname = 'p'
        elif re.match('\s*SECTION\s+\d\s+([A-Z\s]+)', para_text) != None:
           #print ('H2', para_text)
           tagname = 'h2'
        elif re.match('\s*\d\d?\s+[A-Z\s]+$', para_text) != None:
           #print ('H3', para_text)
           tagname = 'h3'
        elif re.match('\s*[\d.]+\s+(([A-Z][a-z])+\s*)+', para_text) != None:
           #print ('H4', para_text)
           tagname = 'h4'
        else:   
           tagname = 'p'

        return tagname   

    def process_para(self, words):
        para_text  = self.get_para_text(words)

        tagname = self.get_tagname(para_text, words)
            
        para_node = Node(self.pos, None, tagname, self.current_node, None)
        self.current_node.add_child(para_node)

        self.text.append(para_text)
        self.pos += len(para_text)
        para_node.end = self.pos

    def add_page_end(self):
        self.pagenum += 1
        node = Node(self.pos, self.pos, 'span', self.current_node,[('class', 'pageend'), ('data-pagenum', '%d' % self.pagenum)])
        self.current_node.add_child(node)

    def process_footnote(self, words):
        node = Node(self.pos, None, 'span', self.current_node,[('class', 'footnote')])
        self.current_node.add_child(node)

        para_text  = self.get_para_text(words)
        #print ('FOOTNOTE', para_text)
        self.text.append(para_text)
        self.pos += len(para_text)
        node.end = self.pos
        
    def get_annotated_doc(self):
        current_node = self.current_node
        while current_node != None:
            current_node.end = self.pos
            current_node = current_node.parent

        doc = ''.join(self.text)
        doc, segmentmap =  annotate_doc(doc, [self.htmlroot])
        doc = '<!DOCTYPE HTML>\n<html>\n<head><meta charset="UTF-8"/></head>' \
              + doc + '</html>'
        return doc


