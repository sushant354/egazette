import re
import magic
from pathlib import Path

def get_file_type(filepath):
    return get_buffer_type(Path(filepath).read_bytes())

def get_buffer_type(buff):

    mtype = magic.from_buffer(buff, mime=True)

    if mtype == 'application/octet-stream':
        s_buff = buff.lstrip()
        if s_buff and s_buff != buff:
            return magic.from_buffer(s_buff, mime=True)

    return mtype


def get_extension(mtype):
    if re.match('text/html', mtype):
        return 'html'
    elif re.match('application/postscript', mtype):
        return 'ps'
    elif re.match('application/pdf', mtype):
        return 'pdf'
    elif re.match('text/plain', mtype):
        return 'txt'
    elif re.match('image/png', mtype):
        return 'png'
    elif re.match('application/msword', mtype):
        return 'doc'
    elif re.match('text/rtf', mtype):
        return 'rtf'
    elif re.match('application/vnd.ms-excel', mtype):
        return 'xls'
    return 'unkwn'

def get_file_extension(doc):
    mtype = get_buffer_type(doc)
    return get_extension(mtype)

