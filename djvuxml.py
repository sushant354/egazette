class Djvu:
    def __init__(self, outhandle):
        self.outhandle = outhandle

    def write_header(self):
        self.outhandle.write('<DjVuXML>\n')
        self.outhandle.write('<BODY>\n')

    def write_page_header(self, height, width, dpi):
        filename = 'file://localhost//var/tmp/autoclean/derive/'
        usemap   = 'tmp.djvu'
        self.outhandle.write('<OBJECT data="%s" height="%d" type="image/x.djvu" usemap="%s" width="%d">\n<PARAM name="PAGE" value="%s"/>\n<PARAM name="DPI" value="%d"/>\n<HIDDENTEXT>\n' % (filename, height, usemap, width, usemap, dpi))

    def write_page_footer(self):
        usemap   = 'tmp.djvu'
        self.outhandle.write('</HIDDENTEXT>\n</OBJECT>\n<MAP name="%s"/>' % usemap)


    def handle_google_response(self, response):
        for page in response.full_text_annotation.pages:
            self.write_page_header(page.height, page.width, 300)

            for block in page.blocks:
                self.outhandle.write('<PAGECOLUMN>\n<REGION>\n')

                for paragraph in block.paragraphs:
                    self.outhandle.write('<PARAGRAPH>\n')
                    self.handle_words(paragraph.words)
                    self.outhandle.write('</PARAGRAPH>\n')

                self.outhandle.write(u'</REGION>\n</PAGECOLUMN>\n')
            self.write_page_footer()

    def write_footer(self):
        self.outhandle.write('</BODY>\n')
        self.outhandle.write('</DjVuXML>\n')


    def is_same_line(self, box1, box2):
        ydiff = box2.vertices[3].y - box2.vertices[0].y
        if ydiff <= 0:
            return True

        numy  = round((box2.vertices[0].y - box1.vertices[0].y) * 1.0/ydiff)

        xdiff =  round(box2.vertices[0].x - box1.vertices[2].x)
        numy = int(numy)
        if numy >= 1 or xdiff <= -50:
            return False
        return True

    def handle_words(self, words):
        lines    = []
        wordlist = []
        prevbox  = None

        for word in words:
            stext = []
            for symbol in word.symbols:
                if symbol.text:
                    stext.append(symbol.text)

            box = word.bounding_box        
            if prevbox == None or not self.is_same_line(prevbox, box):
                if wordlist:
                    lines.append(wordlist)
                wordlist = []

            word_text = u''.join(stext)
            wordlist.append((word_text, box))

            prevbox = box

        if wordlist:
            lines.append(wordlist)

        for line in lines:    
            self.outhandle.write('<LINE>\n')
            for word, box in line:
                self.write_word(word, box)
            self.outhandle.write('</LINE>\n')
     
    def write_word(self, word, box): 
        xmin = box.vertices[0].x
        xmax = box.vertices[1].x
        ymin = box.vertices[0].y
        ymax = box.vertices[3].y

        self.outhandle.write(u'<WORD coords="%d,%d,%d,%d,%d">%s</WORD>\n' % (xmin, ymax, xmax, ymin, ymax, word))

