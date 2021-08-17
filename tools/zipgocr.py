import os
import sys
import shutil
import tarfile
import re

def suffix_to_json(dirpath):
    for filename in os.listdir(dirpath):
        if re.search('\.pickle$', filename):
            new_name, n = re.subn('\.pickle$', '.json', filename)
            filepath1 = os.path.join(dirpath, filename)
            filepath2 = os.path.join(dirpath, new_name)
            os.rename(filepath1, filepath2)

def zip_gocr(dirpath, filename):
    indir = os.path.join(dirpath, filename)
    outfile = os.path.join(dirpath, filename + '.tar.gz')
    tar = tarfile.open(outfile, "w:gz")
    tar.add(indir, arcname=filename)
    tar.close()

    shutil.rmtree(indir)

def traverse(dirpath):
    for filename in os.listdir(dirpath):
        filepath = os.path.join(dirpath, filename)

        if os.path.isdir(filepath):
            if re.search('_gocr$', filename):
                suffix_to_json(filepath)
                zip_gocr(dirpath, filename)
            else:
                traverse(filepath)
        
if __name__ == '__main__':
    datadir = sys.argv[1]

    traverse(datadir)

