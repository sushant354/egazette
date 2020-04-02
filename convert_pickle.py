import os
import sys
import pickle

def convert(filepath1, filepath2):
    if os.path.getsize(filepath1) <= 0:
        #print (filepath1)
        return

    filehandle1 = open(filepath1, 'rb')
    filehandle2 = open(filepath2, 'wb')

    obj = pickle.load(filehandle1, encoding = 'latin1')
    pickle.dump(obj, filehandle2)

    filehandle1.close()
    filehandle2.close()

def convert_dir(dir1, dir2):
    for filename in os.listdir(dir1):
        filepath1 = os.path.join(dir1, filename)
        filepath2 = os.path.join(dir2, filename)
        if os.path.exists(filepath2):
            continue

        convert(filepath1, filepath2)

if __name__ == '__main__':
    filepath1 = sys.argv[1]
    filepath2 = sys.argv[2]
    convert_dir(filepath1, filepath2)
