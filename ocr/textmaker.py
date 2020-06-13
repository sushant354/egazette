from egazette.ocr.gapi import LineWords, get_lines
import re

class TextMaker:
    def __init__(self):
        pass

    def get_left_offset(self, l1, l2, numchars, maxchars):
        #print "OFFSET", numchars, maxchars, page_width, l1, l2
        pix_offset = (maxchars - numchars) * l1 * 1.0/  (self.width - (l2 -l1))

        return int(round(pix_offset))


    def get_word_text(self, word, line_break = True):
        stext = []
        for symbol in word.symbols:
            if symbol.text:
                stext.append(symbol.text)

            if hasattr(symbol.property, 'detected_break'):
                 t = symbol.property.detected_break.type 
                 if t == 1:
                    stext.append(' ')
                 elif t == 5 and line_break:
                    stext.append('\n')

        return ''.join(stext)

    def min_left_offset(self, lines):
        offset = None
        for linewords in lines:
            if linewords.words:
               x = linewords.words[0].bounding_box.vertices[0].x
               if offset == None or x < offset:
                   offset = x
        return offset

    def get_pre_text(self, page):
        page_words = []
        for block in page.blocks:
            for para in block.paragraphs:
                page_words.extend(para.words)
              
        char_width = self.get_char_width(page_words)
        lines      = get_lines(page_words)
        min_left   = self.min_left_offset(lines)
        line_ht    = self.get_avg_ht(lines)

        txtlines   = []
        prevline   = None
        footnotes  = []
        numlines   = len(lines)
        count      = 0

        for linewords in lines:

            if prevline:
                num_lines = self.get_num_lines(prevline, linewords, line_ht)
                txtlines.append('\n' * (num_lines +1))
                if num_lines > 0 and count == numlines - 1:
                    top_offset = self.get_top_offset(linewords)
                    if top_offset >= 0.85 * page.height:
                        footnotes.append(linewords)
                        continue

            txt = self.get_line_text(linewords.words, char_width, min_left)
            txtlines.append(txt)

            prevline = linewords
            count += 1
            
        return txtlines, footnotes

    def get_top_offset(self, line):
        yoffset = None
        for word in line.words:
            v = word.bounding_box.vertices
            if yoffset == None or v[0].y < yoffset:
                yoffset = v[0].y
                
            if v[1].y < yoffset:
                yoffset = v[1].y
                
        return yoffset

    def get_bottom_offset(self, line):
        yoffset = 0
        for word in line.words:
            v = word.bounding_box.vertices
            if v[2].y > yoffset:
                yoffset = v[2].y
                
            if v[3].y > yoffset:
                yoffset = v[3].y
                
        return yoffset


    def get_line_ht(self, line):
        return self.get_bottom_offset(line) - self.get_top_offset(line)

    def get_avg_ht(self, lines):
        ht = 0.0
        for line in lines:
            ht += self.get_line_ht(line)
        return ht / len(lines)    

    def get_num_lines(self, line1, line2, line_ht):
        ydiff = self.get_top_offset(line2) - self.get_bottom_offset(line1)
        return int(round(ydiff /line_ht))


    def get_char_width(self, words):
        prevword  = None
        numchars  = 0
        width     = 0.0

        for word in words:
            numchars += len(word.symbols)
            vertices  = word.bounding_box.vertices
            width    += vertices[1].x - vertices[0].x
        char_width = width/numchars

        return char_width

    def get_num_spaces(self, length, char_width):
        return int((round(length / char_width )))

    def get_line_text(self, words, char_width, min_left):
        line_text = []

        prev_word = None
        for word in words:
            width = word.bounding_box.vertices[0].x
            if prev_word:
                width -= prev_word.bounding_box.vertices[2].x
            else:
                width -= min_left

            num_spaces = self.get_num_spaces(width, char_width)
            prev_word = word

            if num_spaces > 1:
                line_text.append(' ' * (num_spaces -1))

            word_text = self.get_word_text(word, line_break = False)
            line_text.append(word_text)

        return ''.join(line_text)


    def is_all_capstart(self, words):
        for word in words:
            for symbol in word.symbols:
               if symbol.text and re.match('[a-z]', symbol.text):
                   return False
               break
        return True        

