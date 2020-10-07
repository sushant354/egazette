import os
import sys
import re
import subprocess

def convert_dir(dir1, dir2):
    p = subprocess.Popen(['python3', 'convert_pickle.py', dir1, dir2])
    p.wait()

def traverse(dir1, dir2):
    for filename in os.listdir(dir1):
        filepath1 = os.path.join(dir1, filename)
        filepath2 = os.path.join(dir2, filename)

        if os.path.isdir(filepath1):
           if not os.path.exists(filepath2):
               os.mkdir(filepath2)

           if re.search('_gocr$', filepath1):
               convert_dir(filepath1, filepath2)
           else:
               traverse(filepath1, filepath2)


if __name__ == '__main__':
    datadir1 = sys.argv[1]
    datadir2 = sys.argv[2]

    #dill.dill._reverse_typemap['ObjectType'] = object
    traverse(datadir1, datadir2)
