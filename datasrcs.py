import central
import delhi
import bihar
import chattisgarh

srcdict = { \
'central_weekly'       : central.CentralWeekly, \
'central_extraordinary': central.CentralExtraordinary, \
'bihar'                : bihar.Bihar, \
'delhi_weekly'         : delhi.DelhiWeekly, \
'delhi_extraordinary'  : delhi.DelhiExtraordinary, \
'cgweekly'             : chattisgarh.ChattisgarhWeekly, \
'cgextraordinary'      : chattisgarh.ChattisgarhExtraordinary, \
}

srchierarchy = { \
'central'    : ['central_weekly', 'central_extraordinary'], \
'delhi'      : ['delhi_weekly', 'delhi_extraordinary'], \
'chattisgarh': ['cgweekly', 'cgextraordinary'], \
'states'     : ['delhi', 'bihar', 'chattisgarh'] \
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
