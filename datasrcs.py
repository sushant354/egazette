import central
import delhi
import bihar
import chattisgarh
import andhra
import karnataka

import maharashtra
import telangana
import tamilnadu

import odisha
import jharkhand
import madhyapradesh

srcdict = { \
'central_weekly'       : central.CentralWeekly, \
'central_extraordinary': central.CentralExtraordinary, \
'bihar'                : bihar.Bihar, \
'delhi_weekly'         : delhi.DelhiWeekly, \
'delhi_extraordinary'  : delhi.DelhiExtraordinary, \
'cgweekly'             : chattisgarh.ChattisgarhWeekly, \
'cgextraordinary'      : chattisgarh.ChattisgarhExtraordinary, \
'andhra'               : andhra.Andhra, \
'andhraarchive'        : andhra.AndhraArchive, \
'karnataka'            : karnataka.Karnataka, \
'maharashtra'          : maharashtra.Maharashtra, \
'telangana'            : telangana.Telangana, \
'tamilnadu'            : tamilnadu.TamilNadu, \
'odisha'               : odisha.Odisha, \
'jharkhand'            : jharkhand.Jharkhand, \
'madhyapradesh'        : madhyapradesh.MadhyaPradesh, \
}

srchierarchy = { \
'central'    : ['central_weekly', 'central_extraordinary'], \
'delhi'      : ['delhi_weekly', 'delhi_extraordinary'], \
'chattisgarh': ['cgweekly', 'cgextraordinary'], \
'states'     : ['delhi', 'bihar', 'chattisgarh', 'andhra', 'karnataka', \
                'andhraarchive', 'maharashtra', 'telangana', 'tamilnadu', \
                'odisha', 'jharkhand', 'madhyapradesh'] \
}

def get_srcobjs(srclist, storage):
    srcobjs = []

    for src in srclist:
        if src in srchierarchy:
            srcobjs.extend(get_srcobjs(srchierarchy[src], storage))            
        if src in srcdict:
            obj = srcdict[src](src, storage)
            srcobjs.append(obj)

    return srcobjs        
