import central

srcdict = {'central_weekly': central.CentralWeekly, 'central_extraordinary': central.CentralExtraordinary}

srchierarchy = {'central': ['central_weekly', 'central_extraordinary']}

def get_srcobjs(srclist, storage):
    srcobjs = []

    for src in srclist:
        if src in srchierarchy:
            srcobjs.extend(get_srcobjs(srchierarchy[src], storage)) 
        if src in srcdict:
            obj = srcdict[src](src, storage)
            srcobjs.append(obj)

    return srcobjs        
