from xml.sax import saxutils
from lxml import etree 
import numpy as np

def assemble_hocr_title_element(keyvals):
    """
    Create a title="<...>" string from key, value pairs

    Args:

    * keyvals (dict): key value pairs

    Returns: string to insert as title (without the surrounding double quotes)
    """
    r = ''

    for key, val in keyvals.items():
        tot = [key]

        if isinstance(val, list):
            val_list =[]
            for v in val:
               if isinstance(v, int):
                   val_list.append('%d' % v)
               else:
                   val_list.append(v)

            tot += val_list
        elif isinstance(val, int):
            tot.append('%d' % val)
        else:
            tot.append(val)

        r += saxutils.escape(' '.join(tot))
        r += '; '

    if r:
        # Strip off last '; '
        return r[:-2]

    return r



def abbyy_baseline_from_charboxes(charboxes):
    """
    Calculates the baseline of characters part of a single line segment using
    least squares on the center ((left+right)/2) of the bottom of every bounding box.

    Args:

    * charboxes: list of character bounding boxes (which are a list of 4 entries)

    Returns:

    Tuple of m, c (float, int) where m is the increment and c is the offset.
    """
    x = []
    y = []
    for charbox in charboxes:
        # (Left+Right)/2
        x.append((charbox[0] + charbox[2])/2)
        # Bottom
        y.append(charbox[3])

    x = np.array(x)
    y = np.array(y)

    # Normalise to minimal coordinate, maybe we ought to normalise to the first
    # coordinate?
    y -= y.min()

    A = np.vstack([x, np.ones(len(x))]).T

    r = np.linalg.lstsq(A, y, rcond=None)
    m, c = r[0]

    return float(m), int(c)

class HOCR:
    def __init__(self, outhandle, langtags):
        self.outhandle = outhandle
        self.height    = 0
        self.width     = 0
        self.langtags  = langtags
        self.pageno    = 0 

    def write_header(self):
        self.outhandle.write('''<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE html PUBLIC "-//W3C//DTD XHTML 1.0 Transitional//EN" "http://www.w3.org/TR/xhtml1/DTD/xhtml1-transitional.dtd">
<html xmlns="http://www.w3.org/1999/xhtml" xml:lang="en" lang="en">
  <head>
    <title></title>
    <meta http-equiv="Content-Type" content="text/html;charset=utf-8" />
    <meta name="ocr-system" content="Google OCR" />
    <meta name="ocr-capabilities" content="ocr_page ocr_carea ocr_par ocr_line ocrx_word ocrp_wconf ocrp_lang ocrp_dir ocrp_font ocrp_fsize" />
  </head>
  <body>''')
        self.pageno    = 0 
        self.iddict    = {'block': 1, 'par': 1, 'word': 1, 'line': 1}

    def get_id(self, name):
        ret = '%s_%.06d_%.06d' % (name, self.pageno, self.iddict[name])
        self.iddict[name] += 1

        return ret


    def write_footer(self):
        self.outhandle.write('</body>\n</html>\n')


    def process_word(self, word, wordelem):
        for symbol in word.symbols:
            charelem = etree.Element('span', attrib={'class': 'ocrx_cinfo'})
            charelem.text = symbol.text

            kv = {}
            kv['x_bboxes'] = self.get_bbox(symbol.bounding_box)
            kv['x_conf']   = '%6f' % (100 *symbol.confidence)
            charelem.attrib['title'] = assemble_hocr_title_element(kv)
            wordelem.append(charelem)

    def stitch_words(self, words):
        lines    = []
        wordlist = []
        prevbox  = None

        for word in words:
            box = word.bounding_box
            if prevbox == None or not self.is_same_line(prevbox, box):
                if wordlist:
                    lines.append(wordlist)
                wordlist = []

            wordlist.append(word)

            prevbox = box

        if wordlist:
            lines.append(wordlist)

        return lines 

    def get_line_box(self, line):
        l = t = r = b  = None
        
        for word in line:
            box = self.get_bbox(word.bounding_box)

            box_l = box[0]
            box_t = box[1] 
            box_r = box[2]
            box_b = box[3]

            if l == None or l > box_l:
                l = box_l

            if r == None or r < box_r:
                r = box_r

            if t == None or t > box_t:
                t = box_t

            if b == None or b < box_b:
                b = box_b

        if l < 0:
           l = 0
        
        if t < 0:
           t = 0
        
        if r < 0:
           r = 0

        if b < 0:
           b = 0
   
        return [l, t, r, b]
    
    def update_langtag(self, word):
        for lang in word.property.detected_languages:
            self.langtags.update(1, lang.language_code)

    def process_line(self, line, lineelem):
        for word in line:
            wordelem = etree.Element('span', attrib={'class': 'ocrx_word'})

            self.process_word(word, wordelem)
            self.update_langtag(word)

            kv = {'bbox': self.get_bbox(word.bounding_box)}
            kv['x_wconf'] = '%d' % int(100*word.confidence)

            wordelem.attrib['id'] = self.get_id('word')
            wordelem.attrib['title'] =  assemble_hocr_title_element(kv)

            if word.property.detected_languages:
                wordelem.attrib['lang'] = word.property.detected_languages[0].language_code

            lineelem.append(wordelem)

       
    def process_para(self, words, paraelem):
        lines = self.stitch_words(words)

        for line in lines:
            lineelem = etree.Element('span', attrib={'class': 'ocr_line'})

            kv = {}
            kv['bbox'] = self.get_line_box(line)

            cboxes = self.get_charboxes(line)
            m, c = abbyy_baseline_from_charboxes(cboxes)
            kv['baseline'] = '%f %d' % (m, c)

            self.process_line(line, lineelem)

            lineelem.attrib['title'] = assemble_hocr_title_element(kv)
            lineelem.attrib['id'] = self.get_id('line')
            paraelem.append(lineelem)


    def handle_google_response(self, response, ppi, image_path):
        for page in response.full_text_annotation.pages:
            self.handle_page(page, ppi, image_path)

    def handle_page(self, page, ppi, image_path):
        hocr_page = self.process_page(page, ppi, image_path)
        s = etree.tostring(hocr_page, pretty_print=True, method='xml', \
                           encoding='utf-8').decode('utf-8')

        self.outhandle.write(s)
        self.pageno += 1

    def get_bbox(self, box):
        v = box.vertices
        l = min(v[0].x, v[1].x, v[2].x, v[3].x)
        r = max(v[0].x, v[1].x, v[2].x, v[3].x)
        t = min(v[0].y, v[1].y, v[2].y, v[3].y)
        b = max(v[0].y, v[1].y, v[2].y, v[3].y)

        if l < 0:
           l = 0
        
        if t < 0:
           t = 0
        
        if r < 0:
           r = 0

        if b < 0:
           b = 0

        return [l, t, r, b]

    def get_charboxes(self, line):
        cboxes = []
        for word in line:
            for symbol in word.symbols:
                box = self.get_bbox(symbol.bounding_box)
                cboxes.append([box[0], box[1], box[2], box[3]])

        return cboxes

    def process_page(self, page, ppi, image_path):
        kv = {}
        kv['image']    = image_path

        if page:
            kv['bbox'] = ['0', '0', page.width, page.height]
        else:    
            kv['bbox'] = ['0', '0', '0', '0']

        kv['ppageno'] = '%d' % self.pageno

        kv['scan_res'] = '%s %s' % (ppi, ppi)

        pageelem = etree.Element('div', \
                                 attrib={'class': 'ocr_page', \
                                      'id':  'page_%.06d' % self.pageno,\
                                      'title': assemble_hocr_title_element(kv)})

        if page and page.blocks:
            self.handle_blocks(page.blocks, pageelem)

        return pageelem


    def handle_blocks(self, blocks, pageelem):
        for block in blocks:
            kv = {}

            blockelem = etree.Element('div', attrib={'class': 'ocr_carea'})

            kv['bbox'] = self.get_bbox(block.bounding_box)
            blockelem.attrib['title'] = assemble_hocr_title_element(kv)
            blockelem.attrib['id']    = self.get_id('block')

            self.process_block(block, blockelem)
            pageelem.append(blockelem)

        
    def process_block(self, block, blockelem):
        for paragraph in block.paragraphs:
            paraelem = etree.Element('p', attrib={'class': 'ocr_par'})

            paraelem.attrib['id'] = self.get_id('par')
            self.process_para(paragraph.words, paraelem)

            kv = {}
            kv['bbox'] = self.get_bbox(paragraph.bounding_box)

            paraelem.attrib['title'] = assemble_hocr_title_element(kv)
            blockelem.append(paraelem)


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

