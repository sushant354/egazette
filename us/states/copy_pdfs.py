import zipfile
import re
import os
import sys

def unzip(in_path, out_dir):
    f = zipfile.ZipFile(in_path, 'r')
    f.extractall(out_dir)

def copy_pdfs(state_dir, out_dir):
    for filename in os.listdir(state_dir):
        print (filename)
        if re.search('pdf\d*\.zip$', filename):
            unzip(os.path.join(state_dir, filename), out_dir)

def mkdir(filepath):
    if not os.path.exists(filepath):
        os.mkdir(filepath)

if __name__ == '__main__':
    state_dir  = sys.argv[1]
    out_dir    = sys.argv[2]
    state      = sys.argv[3]

    mkdir(out_dir)
    out_dir = os.path.join(out_dir, state)
    mkdir(out_dir)
    out_dir = os.path.join(out_dir, 'admin')
    mkdir(out_dir)

    copy_pdfs(state_dir, out_dir)
