import sys
import os
import logging
import getopt
import re
import io
import subprocess
import tempfile
import codecs

from google.cloud import vision

FNULL = open(os.devnull, 'w')


def print_usage(progname):
    print '''Usage: %s [-l loglevel(critical, error, warn, info, debug)]
                       [-g google_key_file]
                       [-f logfile]
                       [-i input_file] [-o output_file]
          ''' % progname

def get_google_client(key_file):
    os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = key_file
    client = vision.ImageAnnotatorClient()

    return client

def pdf_to_png(infile, pngdir):
    outfile = pngdir + '/%d.png'
    command = ['gs', '-q', '-dNOPAUSE', '-dBATCH',  '-dSAFER', '-r300x300', \
               '-sDEVICE=png16m', '-sOutputFile=%s' % outfile, '-c',  \
               'save', 'pop', '-f',  '%s' % infile]

    p = subprocess.Popen(command, stdout=FNULL, stderr = FNULL)
    p.wait()

    returncode = p.returncode
    if returncode == 0:
        return True
    else:
        return False

def google_ocr(client, input_file, layout = False):
    content = io.open(input_file, 'rb').read()
    image = vision.types.Image(content=content)

    response = client.document_text_detection(image=image)

    if not layout:
        return response.full_text_annotation.text
    
    layout_text = construct_text_layout(response)

    return layout_text

def construct_text_layout(response):    
    pagetext = []
    for page in response.full_text_annotation.pages:
        pagetext.append(get_page_text(page))
    return u'\n\n'.join(pagetext)

def get_left_offset(l1, l2, page_width, numchars, maxchars):
    #print "OFFSET", numchars, maxchars, page_width, l1, l2
    pix_offset = (maxchars - numchars) * l1 * 1.0/  (page_width - (l2 -l1))

    return int(round(pix_offset))

def get_top_offset(t1, t2, pix_per_char):
    pix_offset = t2 - t1
    return int(round(pix_offset * 1.0/pix_per_char))


def get_word_text(words):
    word_text = [] 

    for word in words:
        stext = []
        for symbol in word.symbols:
            if symbol.text:
                stext.append(symbol.text)

            if hasattr(symbol.property, 'detected_break'):
                t = symbol.property.detected_break.type 
                if t == 1:
                    stext.append(u' ')
                '''    
                elif t == 5:
                    stext.append('\n')
                '''    

        box = word.bounding_box
        word_text.append((box, u''.join(stext)))

    return word_text 


def get_page_text(page):
    page_words = []

    for block in page.blocks:
        for paragraph in block.paragraphs:
            word_text = get_word_text(paragraph.words)
            page_words.extend(word_text)

    page_text = stitch_boxes(page_words, page.width)
    return u''.join(page_text)


def get_char_width(page_words):
    prevbox   = None
    maxchars  = 0
    numchars  = 0
    maxwidth  = 0
    width     = 0
    min_width = None

    for box, word_text in page_words:
        if min_width == None or min_width > box.vertices[0].x:
            min_width = box.vertices[0].x

        if prevbox and not is_same_line(prevbox, box):
           
            if numchars > maxchars:
                maxchars = numchars
                maxwidth = width
            numchars = 0
            width    = 0
        numchars += len(word_text)    
        width    += box.vertices[1].x - box.vertices[0].x
        prevbox = box

    if maxchars < numchars:
        maxchars = numchars
        maxwidth = width

    char_width = maxwidth/ maxchars
    if char_width == 0:
        char_width = 1
    if min_width == None:
       min_width = 0

    return char_width, min_width

def get_num_spaces(length, char_width):
    return int(length / char_width )

def get_line_text(line_boxes, char_width, min_width):
    line_text = []

    numchars = 0
    width    = 0 
    prevbox = None
    for box, word_text in line_boxes:
        numchars += len(word_text)
        width += box.vertices[2].x - box.vertices[0].x

        prevbox = box   

    prevbox = None
    for box, word_text in line_boxes:
        if prevbox == None:
            lastpos = min_width
        else:
            lastpos = prevbox.vertices[2].x
        currpos = box.vertices[0].x
        length = currpos - lastpos
        num_spaces = get_num_spaces(length, char_width)
        #print lastpos, currpos, length, num_spaces, char_width, word_text.encode('utf8')

        if num_spaces > 2:
            line_text.append(' ' * num_spaces)

        line_text.append(word_text)

        prevbox = box
   
    return line_text

def is_same_line(box1, box2):
    ydiff = box2.vertices[3].y - box2.vertices[0].y
    if ydiff <= 0:
        return True

    numy  = round((box2.vertices[0].y - box1.vertices[0].y) * 1.0/ydiff)

    xdiff =  round(box2.vertices[0].x - box1.vertices[2].x) 
    numy = int(numy)
    if numy >= 1 or xdiff <= -50: 
        return False
    return True    

def stitch_boxes(page_words, page_width):
    char_width, min_width = get_char_width(page_words)

    page_text  = []
    line_boxes = []
    prevbox    = None

    for box, word_text in page_words:
        #print box
        #print word_text.encode('utf8')
        if prevbox != None and not is_same_line(prevbox, box):
            #print 'BOXES', prevbox.vertices[0],  box.vertices[0]

            page_text.extend(get_line_text(line_boxes, char_width, min_width))

            t2 = box.vertices[0].y
            t1 = prevbox.vertices[3].y
            twidth = (box.vertices[3].y - box.vertices[0].y)
            top_offset  = get_top_offset(t1, t2, twidth)  

            #print 'TOP_OFFSET', t1, t2, twidth, top_offset

            if top_offset < 0:    
                top_offset = 1
            else:
                top_offset += 1

            page_text.append('\n' * top_offset)
            line_boxes = []
        line_boxes.append((box, word_text))       
        prevbox = box
    if line_boxes:
        page_text.extend(get_line_text(line_boxes, char_width, min_width))

    return page_text

def atoi(text):
    return int(text) if text.isdigit() else text

def natural_keys(text):
    return [ atoi(c) for c in re.split('(\d+)', text) ]

def to_text(client, input_file, out_file, layout):
    logger = logging.getLogger('gvision')

    pngdir = tempfile.mkdtemp()

    success = pdf_to_png(input_file, pngdir)

    if not success:
        logger.warn('ghostscript on pdffile %s failed' % input_file)
    else:
        filenames = os.listdir(pngdir)
        filenames.sort(key=natural_keys)

        outhandle = codecs.open(out_file, 'w', encoding = 'utf8')
        for filename in filenames:
            paras = google_ocr(client, os.path.join(pngdir, filename), layout)
            outhandle.write(u'%s' % paras)
            outhandle.write('\n\n\n\n')

    os.system('rm -rf %s' % pngdir)
    outhandle.close()

if __name__ == '__main__':
    progname   = sys.argv[0]
    loglevel   = 'info'
    logfile    = None
    key_file   = None
    input_file = None
    out_file   = None
    layout     = False

    optlist, remlist = getopt.getopt(sys.argv[1:], 'l:f:g:i:o:L')

    for o, v in optlist:
        if o == '-l':
            loglevel = v
        elif o == '-f':
            logfile = v
        elif o == '-g':    
            key_file = v
        elif o == '-i':    
            input_file = v
        elif o == '-o':
            out_file   = v
        elif o == '-L':
            layout = True

    if key_file == None:
        print 'Google Cloud API credentials are mising'
        print_usage(progname)
        sys.exit(0)

    if input_file == None:
        print 'No input file supplied'
        print_usage(progname)
        sys.exit(0)

    if out_file == None:
        print 'No output file specified'
        print_usage(progname)
        sys.exit(0)

    leveldict = {'critical': logging.CRITICAL, 'error': logging.ERROR, \
                 'warning': logging.WARNING,   'info': logging.INFO, \
                 'debug': logging.DEBUG}

    if loglevel not in leveldict:
        print 'Unknown log level %s' % loglevel             
        print_usage(progname)
        sys.exit(0)

    logfmt  = '%(asctime)s: %(name)s: %(levelname)s %(message)s'
    datefmt = '%Y-%m-%d %H:%M:%S'
    if logfile:
        logging.basicConfig(\
            level   = leveldict[loglevel], \
            format  = logfmt, \
            filename = logfile, \
            datefmt = datefmt \
        )
    else:
        logging.basicConfig(\
            level   = leveldict[loglevel], \
            format  = logfmt, \
            datefmt = datefmt \
        )

    client = get_google_client(key_file)
    to_text(client, input_file, out_file, layout)
