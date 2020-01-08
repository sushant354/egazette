import cgi

class HtmlMaker:
    def __init__(self, outhandle):
        self.outhandle  = outhandle
        self.para_break = True

    def write_header(self):
        self.outhandle.write('<!DOCTYPE HTML>\n<html>\n')

    def write_footer(self):
        self.outhandle.write('</html>')

    def write_page(self, response):
        for page in response.full_text_annotation.pages:
            ordered_blocks = self.order_blocks(page.blocks, page.width, \
                                               page.height)   
            for category, block in ordered_blocks:
                self.print_block(block)

    def classify_block(self, block, width, height):
        left  = (block.bounding_box.vertices[0].x * 100/width)
        right = (block.bounding_box.vertices[1].x * 100/width)
        top   = (block.bounding_box.vertices[0].y * 100/height)
        bottom = (block.bounding_box.vertices[2].y * 100/height)

        if bottom >= 90:
            return 'footnote', 'footnote'
        if abs(left + right - 100) <= 10:
            return '1st', 'center'

        if right <= 55:
            return '1st', 'left_column'

        if left >= 45:    
            return '2nd', 'right_column'
        return '1st', 'center'

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

    def print_block(self, block):
        #print (block.bounding_box.vertices)
        for para in block.paragraphs:
            self.outhandle.write('<p>')
            para_text = self.handle_words(para.words)
            #print ('----------------------------')
            #print (para_text)
            self.outhandle.write(cgi.escape(para_text))
            self.outhandle.write('</p>\n\n')
    
    def handle_words(self, words):
        wordlist = []

        for word in words:
            #print (word)
            stext = []
            for symbol in word.symbols:
                if symbol.text:
                    stext.append(symbol.text)

                if hasattr(symbol.property, 'detected_break'):
                    t = symbol.property.detected_break.type
                    #print (symbol.text, t)
                    if t == 1 or t == 3:
                        stext.append(' ')
                    elif t == 5:
                        stext.append('\n')

            wordlist.append(''.join(stext))

        return ''.join(wordlist)
