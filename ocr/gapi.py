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

def is_y_overlap(word1, word2):
    v1 = word1.bounding_box.vertices
    v2 = word2.bounding_box.vertices

    if (v2[0].y >= v1[0].y and v2[0].y <= v1[2].y) or (v2[2].y >= v1[0].y and v2[2].y <= v1[2].y):
        return True
    return False    

def get_lines(words):
    words.sort(key = lambda word: word.bounding_box.vertices[0].y)

    linewords = LineWords()
    lines = [linewords]

    prev_word = None
    for word in words:
        if prev_word and not is_y_overlap(prev_word, word):
            linewords = LineWords()
            lines.append(linewords)
        prev_word = word
        linewords.add_word(word)
    
    for linewords in lines:
       linewords.words.sort(key = lambda word: word.bounding_box.vertices[0].x)
    return lines
    
def get_word_text(word):
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

