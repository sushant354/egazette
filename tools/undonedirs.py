import os
import sys
import shutil

if __name__ == '__main__':
    basedir = sys.argv[1]

    for filename in os.listdir(basedir):
        filepath = os.path.join(basedir, filename)
        fnames = os.listdir(filepath)

        success = False
        for f in fnames:
            if f.endswith('_abbyy.gz'):
                success = True
                break

        if not success:
            print (filename)
            shutil.rmtree(filepath)
