import sys
import os
import re
import subprocess
import tempfile
from PIL import Image
from PIL import ImageFilter



def is_black(color, sub_limit):
    max_c = max(color[:3])
    min_c = min(color[:3])
    if color[0] <= sub_limit  and color[1] <= sub_limit and \
            color[2] <= sub_limit and (max_c - min_c) < 10:
        return True
    return False    

def find_black(colors):
    i = 0
    sel = None
    while i < len(colors):
        if is_black(colors[i], 0):
            return True 
        i += 1

    return  False
def find_white(colors):
    i = 0
    sel = None
    while i < len(colors):
        if is_white(colors[i], 254):
            return True 
        i += 1

    return  False


def is_white(color, sub_limit):
    max_c = max(color[:3])
    min_c = min(color[:3])
    return color[0] > sub_limit and color[1] > sub_limit and color[2] > sub_limit and (max_c - min_c) < 10

def shdbe_white(left, right, top, bottom):
    doms = []
    doms.append(find_non_black(left))
    doms.append(find_non_black(right))
    doms.append(find_non_black(top))
    doms.append(find_non_black(bottom))

    x = 0
    for dom in doms:
        if dom and is_white(dom, 200):
            x += 1
    print(x)        
    return x>=2

def haryana_captcha(img):
    m = 2.5
    img = img.resize((int(img.size[0]*m), int(img.size[1]*m)))
    #img = img.convert('L') # convert image to single channel greyscale
    val = tesseract(img)
    if val:
        return val.lower()
    return val    

def bis_captcha(img):
    val = tesseract(img)
    return val

def resize(img):
    m = 2.0 
    img = img.resize((int(img.size[0]*m), int(img.size[1]*m))).convert('RGBA')
    return img

def is_grey(color):
    return is_white(color, 130) and is_black(color, 150)

def make_white(pixdata, x, y):
    pixdata[x, y] = (255, 255, 255, 255)

def ecourt(img, outfile = None):
    """Make text more clear by thresholding all pixels above / below this limit to white / black
    """
    sub_limit = 10
    # resize to make more clearer
    try:
        img = img.convert('RGBA')
    except IOError:
        return None

    pixdata = img.load()

    for y in range(img.size[1]):
        for x in range(img.size[0]):
            if is_black(pixdata[x, y], 100):
                # make dark color black
                pixdata[x, y] = (0, 0, 0, 255)
            else:
                # make light color white
                pixdata[x, y] = (255, 255, 255, 255)

    img2 = img.copy()
    dilate(img, pixdata, 4, True)
    width, height = img.size                
    img = img.convert('L') # convert image to single channel greyscale
    if outfile:
        img.save(outfile)
    val = tesseract(img)
    if not val or len(val) != 5:
        val = tesseract(img2.convert('L'))
    return val

def remove_lines(img, chop):
    data = img.load()
    width, height = img.size
     
    # Iterate through the rows.
    for y in range(height):
        for x in range(width):

            # Make sure we're on a dark pixel.
            if data[x, y] > 128:
                continue

            # Keep a total of non-white contiguous pixels.
            total = 0

            # Check a sequence ranging from x to image.width.
            for c in range(x, width):

                # If the pixel is dark, add it to the total.
                if data[c, y] < 128:
                    total += 1

                # If the pixel is light, stop the sequence.
                else:
                   break

            # If the total is less than the chop, replace everything with white.
            if total <= chop:
                for c in range(total):
                    data[x + c, y] = 255

            # Skip this sequence we just altered.
            x += total


    # Iterate through the columns.
    for x in range(width):
        for y in range(height):

            # Make sure we're on a dark pixel.
            if data[x, y] > 128:
                continue

            # Keep a total of non-white contiguous pixels.
            total = 0

            # Check a sequence ranging from y to image.height.
            for c in range(y, height):

                # If the pixel is dark, add it to the total.
                if data[x, c] < 128:
                    total += 1

                # If the pixel is light, stop the sequence.
                else:
                    break

            # If the total is less than the chop, replace everything with white.
            if total <= chop:
                for c in range(total):
                    data[x, y + c] = 255

            # Skip this sequence we just altered.
            y += total

def nh_score(img, cycles, threshold):
    data = img.load()
    width, height = img.size
    score = []
    for x in range(width):
        colscore = []
        for y in range(height):
            if data[x, y] < 128:
                p = 1
            else:
                p = 0
            colscore.append(p)
        score.append(colscore)

    for i in range(cycles):
        for x in range(width):
            colscore = score[x]
            for y in range(height):
                if colscore[y] > 0:
                    if x > 0:
                        colscore[y] += score[x-1][y]
                    if x < width -1:
                        colscore[y] += score[x+1][y]
                    if y > 0:
                        colscore[y] += colscore[y-1]
                    if y < height -1:    
                        colscore[y] += colscore[y+1]
    for x in range(width):
        colscore = []
        for y in range(height):
            if score[x][y] <=  threshold:
                data[x, y] = 255
                            


def himachal(img, outfile = None):
    m = 2 
    #img = img.resize((int(img.size[0]*m), int(img.size[1]*m)))
    img = img.convert('L') # convert image to single channel greyscale

    nh_score(img, 10, 10000 * 1000 * 1000)
    if outfile:
        img.save(outfile)

    #img = img.resize((int(img.size[0]*m), int(img.size[1]*m)))
    val = tesseract(img)
    return val

def allahabad(img, outfile = None):
    img = img.convert('RGBA')
    pixdata = img.load()

    for y in range(img.size[1]):
        for x in range(img.size[0]):
            if pixdata[x, y][0] < 100:
                 # make dark color black
                pixdata[x, y] = (255, 255, 255, 255)
            else:
                pixdata[x, y] = (0, 0, 0, 255)
                # make light color white
    dilate(img, pixdata, 3, False)

    img = img.convert('L') # convert image to single channel greyscale
    if outfile:
        img.save(outfile)

    val = tesseract(img)
    return val 

def dilate(img, pixdata, window, change_after):
    black = []
    for y in range(img.size[1]):
        for x in range(img.size[0]):
            if is_white(pixdata[x, y], 254)  and \
                    x >= window and y >= window and \
                    x+window < img.size[0] and y + window < img.size[1] and \
                    shdbe_black(pixdata, x, y, window):
                if change_after:
                    black.append((x, y))
                else:
                    pixdata[x, y] = (0, 0, 0, 255)
    for x, y in black:            
        pixdata[x, y] = (0, 0, 0, 255)

def shdbe_black(pixdata, x, y, window):
    left = []
    for i in range(1, window+1):
        left.append(pixdata[x-i, y])

    right = []
    for i in range(1, window+1):
        right.append(pixdata[x+i, y])

    top = []    
    for i in range(1, window+1):
        top.append(pixdata[x, y-i])

    bottom = []    
    for i in range(1, window+1):
        bottom.append(pixdata[x, y+i])

    x = 0
    if find_black(left):
        x += 1
    if find_black(right):
        x += 1
    if find_black(top):
        x += 1
    if find_black(bottom):
        x += 1
    return x >=3

def call_command(*args):
    """call given command arguments, raise exception if error, and return output
    """
    c = subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    output, error = c.communicate()
    if c.returncode != 0:
        if error:
            print(error)
        print("Error running `%s'" % ' '.join(args))
    return output


def tesseract(image):
    """Decode image with Tesseract  
    """
    # create temporary file for tiff image required as input to tesseract
    input_file = tempfile.NamedTemporaryFile(suffix='.tif')
    image.save(input_file.name)

    # perform OCR
    output_filename = input_file.name.replace('.tif', '.txt')
    call_command('tesseract', '--psm', '7', input_file.name, output_filename.replace('.txt', ''))
    
    # read in result from output file
    result = open(output_filename).read()
    os.remove(output_filename)
    return clean(result)


def clean(s):
    """Standardize the OCR output
    """
    # remove non-alpha numeric text
    return re.sub('[\W]', '', s)



if __name__ == '__main__':
    directory = sys.argv[1]
    if len(sys.argv) >= 3:
        outdir    = sys.argv[2]
    else:
        outdir = None

    results = {}
    fhandle = open(os.path.join(directory, 'results.txt'))
    for line in fhandle:
        words = line.split()
        results[words[0].strip()] = words[1].strip()

    success = failed = noresult = 0

    filenames = os.listdir(directory)
    for filename in filenames:
        if filename.endswith('.png') or filename.endswith('.jpeg'):
            f = os.path.join(directory, filename)
            img = Image.open(f)

            if outdir:
                outfile = os.path.join(outdir, filename)
            else:
                outfile = None

            val =   haryana_captcha(img)
            print(val)
            if val:
                expected = results[filename]
                if val == expected:
                    success += 1
                else:
                    print(filename, val, expected)
                    failed += 1
            else:
                noresult += 1
    print('Success: ', success, 'Failed: ', failed, 'No Result: ', noresult)


