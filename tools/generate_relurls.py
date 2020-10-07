import sys
from egazette.utils.file_storage import FileManager

if __name__ == '__main__':
    progname = sys.argv[0]
    srcname  = sys.argv[1]
    datadir  = sys.argv[2]

    storage = FileManager(datadir, False, False)

    for relurl in storage.find_matching_relurls([srcname], None, None):
        print (relurl)
