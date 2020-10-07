import os
import sys
import re
import shutil

def find_matching_dirs(dirname):
    for filename in os.listdir(dirname):
        filepath = os.path.join(dirname, filename)
        if os.path.isdir(filepath):
            if re.search('_(jpg|jp2)$', filename):
                yield filepath
            else:
                for subfilepath in find_matching_dirs(filepath):
                    yield subfilepath

def find_matching_files(dirname):
    for filename in os.listdir(dirname):
        filepath = os.path.join(dirname, filename)
        if os.path.isfile(filepath) and re.search('_(jp2|jpg)\.zip', filename):
            yield filepath
        elif os.path.isdir(filepath):
            for subfilepath in find_matching_files(filepath):
                yield subfilepath


if __name__ == '__main__':
    dirname = sys.argv[1]
    for filepath in find_matching_dirs(dirname):
        print(filepath)
        shutil.rmtree(filepath)

    for filepath in find_matching_files(dirname):
        print(filepath)
        os.remove(filepath)
