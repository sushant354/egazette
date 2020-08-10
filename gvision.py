import sys
import os
import logging
import getopt
import re
import io
import subprocess
import tempfile
import codecs
import pickle
from zipfile import ZipFile
import gzip
import time
import shutil

from egazette.ocr.djvuxml import Djvu
from egazette.ocr.abbyxml import Abby
from egazette.ocr.htmlmaker import HtmlMaker
import internetarchive 
from internetarchive import download, upload, get_session, modify_metadata

from google.cloud import vision

FNULL = open(os.devnull, 'w')


def print_usage(progname):
    print('''Usage: %s [-l loglevel(critical, error, warn, info, debug)]
                       [-D top_dir for InternetArchive mode]
                       [-a access_key] [-k secret_key]
                       [-d jpg_dir (intermediate jpg files)]
                       [-g google_ocr_output_directory]
                       [-f jp2_filter]
                       [-F logfile]
                       [-O output_format(text|djvu|abby|html)]
                       [-G google_key_file]
                       [-m internetarchive_item]
                       [-s (stdin for streaming internetarchive_items)]
                       [-I file with internetarchive_items]
                       [-i input_file] [-o output_file]
                       [-u (update)]
          ''' % progname)

def get_google_client(key_file):
    os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = key_file
    client = vision.ImageAnnotatorClient()

    return client

def pdf_to_jpg(infile, jpgdir, ppi):
    itemname = os.path.splitext(os.path.basename(infile))[0]

    outfile = os.path.join(jpgdir, itemname+ '_%04d.jpg')

    command = ['gs', '-q', '-dNOPAUSE', '-dBATCH',  '-dSAFER', \
               '-r%dx%d' % (ppi, ppi), \
               '-sDEVICE=jpeg', '-sOutputFile=%s' % outfile, '-c',  \
               'save', 'pop', '-f',  '%s' % infile]

    p = subprocess.Popen(command, stdout=FNULL, stderr = FNULL)
    p.wait()

    returncode = p.returncode
    if returncode == 0:
        return True
    else:
        return False

def google_ocr(client, input_file, gocr_file):
    if gocr_file and os.path.exists(gocr_file):
        pickle_in = open(gocr_file, 'rb')
        return pickle.load(pickle_in)
        
    content = io.open(input_file, 'rb').read()
    image = vision.types.Image(content=content)

    try:
        response = client.document_text_detection(image=image)
    except Exception as e:
        logger = logging.getLogger('gvision.ocr')
        logger.warn('Error in Google Vision API for %s %s', input_file, e)
        return None

    if gocr_file:
        pickle_out = open(gocr_file, 'wb')
        pickle.dump(response, pickle_out)
        pickle_out.close()

    return response

def get_text(response, layout):
    if layout:
        text = construct_text_layout(response)
    else:    
        text = response.full_text_annotation.text

    return text

def construct_text_layout(response):    
    pagetext = []
    for page in response.full_text_annotation.pages:
        pagetext.append(get_page_text(page))
    return '\n\n'.join(pagetext)

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
                    stext.append(' ')
                elif t == 5:
                    stext.append('\n')

        box = word.bounding_box
        word_text.append((box, ''.join(stext)))

    return word_text 


def get_page_text(page):
    page_words = []

    for block in page.blocks:
        for paragraph in block.paragraphs:
            word_text = get_word_text(paragraph.words)
            page_words.extend(word_text)

    page_text = stitch_boxes(page_words, page.width)
    return ''.join(page_text)


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

def process(client, jpgdir, outhandle, out_format, gocr_dir, layout, ppi):
    filenames = os.listdir(jpgdir)
    filenames.sort(key=natural_keys)

    if out_format == 'text':
        to_text(jpgdir, filenames, client, outhandle, gocr_dir)
    elif out_format == 'html':
        to_html(jpgdir, filenames, client, outhandle, gocr_dir)
    elif out_format == 'djvu':   
        to_djvu(jpgdir, filenames, client, outhandle, gocr_dir)
    elif out_format == 'abby':   
        to_abby(jpgdir, filenames, client, outhandle, gocr_dir, ppi)


def to_text(jpgdir, filenames, client, outhandle, gocr_dir):
    for filename in filenames:
        infile    = os.path.join(jpgdir, filename)
        if gocr_dir:
            gocr_file, n =  re.subn('jpg$', 'pickle', filename)
            gocr_file = os.path.join(gocr_dir, gocr_file)
        else:
            gocr_file = None
        response  = google_ocr(client, infile, gocr_file)

        if response:
            paras = get_text(response, layout)
            outhandle.write('%s' % paras)
            outhandle.write('\n\n\n\n')

def to_html(jpgdir, filenames, client, outhandle, gocr_dir):
    htmlmaker = HtmlMaker(outhandle)
    htmlmaker.write_header()
    for filename in filenames:
        infile    = os.path.join(jpgdir, filename)
        if gocr_dir:
            gocr_file, n =  re.subn('jpg$', 'pickle', filename)
            gocr_file = os.path.join(gocr_dir, gocr_file)
        else:
            gocr_file = None
        response  = google_ocr(client, infile, gocr_file)

        if response:
            htmlmaker.write_page(response)
    htmlmaker.write_footer()

def to_djvu(jpgdir, filenames, client, outhandle, gocr_dir):
    djvu = Djvu(outhandle)
    djvu.write_header()
    for filename in filenames:
        infile    = os.path.join(jpgdir, filename)

        if gocr_dir:
            gocr_file, n =  re.subn('jpg$', 'pickle', filename)
            gocr_file = os.path.join(gocr_dir, gocr_file)
        else:
            gocr_file = None
        response  = google_ocr(client, infile, gocr_file)
        if response:
            djvu.handle_google_response(response)
    djvu.write_footer()

def to_abby(jpgdir, filenames, client, outhandle, gocr_dir, ppi):
    logger = logging.getLogger('gvision')
    abby= Abby(outhandle)
    abby.write_header()
    for filename in filenames:
        infile    = os.path.join(jpgdir, filename)
        if gocr_dir:
            gocr_file, n =  re.subn('jpg$', 'pickle', filename)
            gocr_file = os.path.join(gocr_dir, gocr_file)
        else:
            gocr_file = None
        response  = google_ocr(client, infile, gocr_file)
        if response and response.full_text_annotation.pages:
            abby.handle_google_response(response, ppi)
        else:
            logger.warn('No pages in %s', filename)
            abby.write_page_header(None, None, ppi)
            abby.write_page_footer()

    abby.write_footer()

def compress_abbyy(abby_file, compressed_file):
    f_in = open(abby_file, 'rb')
    f_out = gzip.open(compressed_file, 'wb')
    f_out.writelines(f_in)
    f_out.close()
    f_in.close()

class IA:
    def __init__(self, top_dir, access_key, secret_key, loglevel, logfile):
        self.top_dir      = top_dir
        self.access_key   = access_key
        self.secret_key   = secret_key
        self.headers      = {'x-archive-keep-old-version': '0'}

        session_data = {'access': access_key, 'secret': secret_key}
        if logfile:
            logconfig    = {'logging': {'level': loglevel, 'file': logfile}}
        else:
            logconfig    = {'logging': {'level': loglevel}}

        self.session = get_session({'s3': session_data, 'logging': logconfig})
        self.logger = logging.getLogger('gvision.ia')

    def delete_imagepdf(self, item, abby_filegz):
        head, abby_file = os.path.split(abby_filegz)
        pdffile = re.sub('_abbyy.gz$', '.pdf', abby_file)

        itemobj = internetarchive.get_item(item)
        fileobj = internetarchive.File(itemobj, pdffile)
        if fileobj and fileobj.source == 'derivative' and \
                fileobj.format == 'Image Container PDF':
            fileobj.delete(access_key = self.access_key, headers= self.headers,\
                           secret_key = self.secret_key)    
            self.logger.warn('Old image pdf exists in %s. Deleted it', item)



    def find_jp2(self, item_path):
        zfiles = []
        for filename in os.listdir(item_path):
            if re.search('_jp2.zip$', filename):
                zfiles.append(filename)
        return zfiles        

    def download_jp2(self, item, glob_pattern):
        success = False
        while not success:
            try:
                download(item, glob_pattern=glob_pattern, destdir=self.top_dir,\
                         ignore_existing = True, retries = 10)
                success = True         
            except Exception as e:
                success = False
                time.sleep(60)

    def is_exist(self, item):
        item_path = os.path.join(self.top_dir, item)
        if os.path.exists(item_path):
            return True
        return False    

    def fetch_jp2(self, item, jp2_filter):
        item_path = os.path.join(self.top_dir, item)
        if jp2_filter:
            for f in jp2_filter:
                self.download_jp2(item, '%s*_jp2.zip' % f)
        else:        
            self.download_jp2(item, '*_jp2.zip')
                
        if not os.path.exists(item_path):
            self.logger.warn('Item path does not exist: %s', item_path)
            return [] 

        return self.find_jp2(item_path)

    def extract_jp2(self, item, zfile): 
        item_path = os.path.join(self.top_dir, item)
        jp2_dir,n = re.subn('\.zip$', '', zfile)
        jp2_dir   = os.path.join(item_path, jp2_dir)

        if not zfile:        
            self.logger.warn('JP2 zip file does not exist: %s', item)
            return None 
        
        if os.path.exists(jp2_dir):        
            self.logger.info('JP2 dir already exists. No need to extract %s', item)
            return jp2_dir

        z = ZipFile(os.path.join(item_path, zfile))
        z.extractall(item_path)
        return jp2_dir 


    def jp2_to_jpg(self, jp2file, jpgfile):
        command = ['convert', jp2file, jpgfile]
        p = subprocess.Popen(command, stdout=FNULL, stderr = FNULL)
        return p

    def convert_jp2(self, jp2_path):
        if not jp2_path:        
            self.logger.warn('JP2 path does not exist: %s', jp2_path)
            return None

        jpg_path, n = re.subn('_jp2$', '_jpg', jp2_path)
        if not os.path.exists(jpg_path):
            os.mkdir(jpg_path)

        plist = []
        for filename in os.listdir(jp2_path):
            jp2file = os.path.join(jp2_path, filename)
            jpgfile, n = re.subn('.jp2$', '.jpg', filename)
            jpgfile = os.path.join(jpg_path, jpgfile)

            if not os.path.exists(jpgfile):
                p = self.jp2_to_jpg(jp2file, jpgfile)
                plist.append(p)
                if len(plist) >= 5:
                    for p in plist:
                       p.wait()
                    plist = []   

        
        for p in plist:
            p.wait()

        return jpg_path


    def update_metadata(self, identifier, metadata):
        success = False
        count = 1
        while not success:
            success = self.ia_modify_metadata(identifier, metadata)
            if not success:
                count += 1
                self.logger.info('Metadata failed for %s. Rety %d time', identifier, count)
                time.sleep(300)

        self.logger.info('Updated metadata for %s', identifier)

    def ia_modify_metadata(self, identifier, metadata):
        try:
            modify_metadata(identifier, metadata = metadata, \
                            access_key = self.access_key, \
                            secret_key = self.secret_key)
        except Exception as e:
            self.logger.warn('Could not  modify metadata %s. Error %s' , identifier, e)
            return False
        return True

    def upload_abbyy(self, ia_item, abby_filelist):
        metadata = {'ocr': 'google-cloud-vision IndianKanoon 1.0', \
                    'fts-ignore-ingestion-lang-filter': 'true'}

        abby_files_gz = []
        for abby_file in abby_filelist:
            abby_file_gz, n = re.subn('xml$', 'gz', abby_file)
            self.delete_imagepdf(ia_item, abby_file_gz)

            compress_abbyy(abby_file, abby_file_gz)
            abby_files_gz.append(abby_file_gz)

        self.update_metadata(ia_item, metadata)
        success = False 
        while not success:
            try:
                success = upload(ia_item, abby_files_gz, headers=self.headers,\
                                 access_key = self.access_key, \
                                 secret_key = self.secret_key, retries=100)
                success = True                 
            except Exception as e:
                self.logger.warn('Error in upload for %s: %s', ia_item, e)
                success = False
                time.sleep(120)
        return success   

def process_item(client, ia, ia_item, jp2_filter, out_format, update, ppi):
        if not update and ia.is_exist(ia_item):
            logger.warn('Item already processed %s', ia_item)
            return

        zfiles = ia.fetch_jp2(ia_item, jp2_filter)

        if not zfiles:
            logger.warn('Could not get JP2 files for %s', ia_item)
            return 

        
        inter_files = []
        abby_files  = []
        item_path   = os.path.join(ia.top_dir, ia_item)

        for zfile in zfiles:   
            inter_files.append(('file', os.path.join(item_path, zfile)))

            jp2_path = ia.extract_jp2(ia_item, zfile)   
            if not jp2_path:
                logger.warn('JP2 files not extracted %s', zfile)
                continue
            
            inter_files.append(('dir', jp2_path))

            jpgdir   = ia.convert_jp2(jp2_path)
            if not jpgdir:
                logger.warn('Could not convert JP2 to JPG for %s', jp2_path)
                continue

            inter_files.append(('dir', jpgdir))

            gocr_dir, n = re.subn('_jpg$', '_gocr', jpgdir)
            if not os.path.exists(gocr_dir):
                os.mkdir(gocr_dir)

            if out_format == 'abby':
                out_file, n = re.subn('_jpg$', '_abbyy.xml', jpgdir)   
            elif out_format == 'text':
                out_file, n = re.subn('_jpg$', '.txt', jpgdir)   
            elif out_format == 'djvu':
                out_file, n = re.subn('_jpg$', '.djvu', jpgdir)
            elif out_format == 'html':
                out_file, n = re.subn('_jpg$', '.html', jpgdir)

            outhandle = codecs.open(out_file, 'w', encoding = 'utf8')
            process(client, jpgdir, outhandle, out_format, gocr_dir, layout, \
                    ppi)
            outhandle.close()

            if out_format == 'abby':
                abby_files.append(out_file)
    
        if out_format == 'abby':
            ia.upload_abbyy(ia_item, abby_files)

        clean_datadir(inter_files)

def clean_datadir(inter_files):
    for filetype, filepath in inter_files:
        if filetype == 'file':
            os.remove(filepath)
        else:    
            shutil.rmtree(filepath)

def is_processed(ia_item, check_dirs):
    for dirname in check_dirs:
        filepath = os.path.join(dirname, ia_item)
        if os.path.exists(filepath):
            return True
    return False

if __name__ == '__main__':
    progname   = sys.argv[0]
    loglevel   = 'info'
    logfile    = None
    key_file   = None
    input_file = None
    out_file   = None
    out_format = 'text'
    layout     = False
    gocr_dir   = None
    top_dir    = None
    access_key = None
    secret_key = None
    ia_item    = None
    jp2_filter = []
    update     = False
    ppi        = 300
    ia_item_file = None
    check_dirs   = []

    optlist, remlist = getopt.getopt(sys.argv[1:], 'a:c:d:D:l:f:F:g:G:i:I:k:m:o:O:p:Lsu')

    jpgdir = None
    for o, v in optlist:
        if o == '-d':
            jpgdir = v
        elif o == '-D':
            top_dir = v
        elif o == '-c':
            check_dirs.append(v)
        elif o == '-l':
            loglevel = v
        elif o == '-F':
            logfile = v
        elif o == '-f':
            jp2_filter.append(v)
        elif o == '-g':
            gocr_dir = v
        elif o == '-G':    
            key_file = v
        elif o == '-i':    
            input_file = v
        elif o == '-m':
            ia_item =v
        elif o == '-I':
            ia_item_file = codecs.open(v, 'r', encoding = 'utf8')
        elif o == '-p':
            ppi = int(v)
        elif o == '-s':
            ia_item_file = sys.stdin
        elif o == '-a':
            access_key = v
        elif o == '-k':
            secret_key = v
        elif o == '-o':
            out_file   = v
        elif o == '-L':
            layout = True
        elif o == '-O':
            out_format = v
        elif o == '-u':
            update = True

    if key_file == None:
        print('Google Cloud API credentials are mising')
        print_usage(progname)
        sys.exit(0)

    leveldict = {'critical': logging.CRITICAL, 'error': logging.ERROR, \
                 'warning': logging.WARNING,   'info': logging.INFO, \
                 'debug': logging.DEBUG}

    if loglevel not in leveldict:
        print('Unknown log level %s' % loglevel)             
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

    logger = logging.getLogger('gvision')

    if ia_item and check_dirs and is_processed(ia_item, check_dirs):
        logger.warn('Item is already processed. Exiting %s', ia_item)
        sys.exit(0)

    ia = None
    if top_dir:
        if input_file or out_file:
            print('In InternetArchive mode, you should not specify input_file or output_file')
            print_usage(progname)
            sys.exit(0)

        if secret_key == None or access_key == None or \
                (ia_item == None and ia_item_file == None):
            print('In InternetArchive mode, you need to specify item, secret_key and access_key')
            print_usage(progname)
            sys.exit(0)

        
    if top_dir == None and input_file == None:
        print('No input file supplied')
        print_usage(progname)
        sys.exit(0)

    if top_dir == None and out_file == None:
        print('No output file specified')
        print_usage(progname)
        sys.exit(0)

    if out_format not in ['text', 'djvu', 'abby', 'html']:
        print('Unsupported output format %s. Output format should be text or djvu.' % out_format)
        print_usage(progname)
        sys.exit(0)

    client = get_google_client(key_file)
    tmpdir = False

    ia = None
    if input_file:
        if jpgdir == None:
            jpgdir = tempfile.mkdtemp()
            tmpdir = True

        success = pdf_to_jpg(input_file, jpgdir, ppi)

        if not success:
            logger.warn('ghostscript on pdffile %s failed' % input_file)
            sys.exit(0)
        outhandle = codecs.open(out_file, 'w', encoding = 'utf8')
        process(client, jpgdir, outhandle, out_format, gocr_dir, layout, ppi)
        outhandle.close()

        if tmpdir:
           os.system('rm -rf %s' % jpgdir)
    else:
        ia = IA(top_dir, access_key, secret_key, leveldict[loglevel], logfile)
        if ia_item:
            process_item(client, ia, ia_item, jp2_filter, out_format, update, ppi)
        elif ia_item_file:
            for ia_item in ia_item_file:
                ia_item = ia_item.strip()
                process_item(client, ia, ia_item, jp2_filter, out_format, update, ppi)
        
