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

import punjab
import uttarakhand
import haryana

import kerala
import himachal

import stgeorge

import goa
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
'punjab'               : punjab.Punjab, \
'uttarakhand'          : uttarakhand.Uttarakhand, \
'himachal'             : himachal.Himachal, \
'haryana'              : haryana.Haryana, \
'haryanaarchive'       : haryana.HaryanaArchive, \
'kerala'               : kerala.Kerala, \
'stgeorge'             : stgeorge.StGeorge, \
'keralalibrary'        : stgeorge.KeralaLibrary, \
'goa'                  : goa.Goa, \
}

srcnames = { \
'central_weekly'       : 'Government of India', \
'central_extraordinary': 'Government of India', \
'bihar'                : 'Government of Bihar', \
'delhi_weekly'         : 'Government of NCT of Delhi', \
'delhi_extraordinary'  : 'Government of NCT of Delhi', \
'cgweekly'             : 'Government of Chattisgarh', \
'cgextraordinary'      : 'Government of Chattisgarh', \
'andhra'               : 'Government of Andhra Pradesh', \
'andhraarchive'        : 'Government of Andhra Pradesh', \
'karnataka'            : 'Government of Karnataka', \
'maharashtra'          : 'Government of Maharashtra', \
'telangana'            : 'Government of Telangana', \
'tamilnadu'            : 'Government of Tamil Nadu', \
'odisha'               : 'Government of Odisha', \
'jharkhand'            : 'Government of Jharkhand', \
'madhyapradesh'        : 'Government of Madhya Pradesh', \
'punjab'               : 'Government of Punjab', \
'uttarakhand'          : 'Government of Uttarakhand', \
'himachal'             : 'Government of Himachal Pradesh', \
'haryana'              : 'Government of Haryana', \
'haryanaarchive'       : 'Government of Haryana', \
'kerala'               : 'Government of Kerala', \
'stgeorge'             : 'Madras Presidency', \
'keralalibrary'        : 'Government of Kerala', \
'goa'                  : 'Government of Goa', \
}

categories = { \
'central_weekly'       : 'Gazette of India - Weekly', \
'central_extraordinary': 'Gazette of India - Extraordinary', \
'bihar'                : 'Bihar Gazette', \
'delhi_weekly'         : 'Delhi Gazette - Weekly', \
'delhi_extraordinary'  : 'Delhi Gazette - Extraordinary', \
'cgweekly'             : 'Chattisgarh Gazette - Weekly', \
'cgextraordinary'      : 'Chattisgarh Gazette - Extraordinary', \
'andhra'               : 'Andhra Pradesh Gazette', \
'andhraarchive'        : 'Andhra Pradesh Gazette', \
'karnataka'            : 'Karnataka Gazette', \
'maharashtra'          : 'Maharashtra Gazette', \
'telangana'            : 'Telangana Gazette', \
'tamilnadu'            : 'Tamil Nadu Gazette', \
'odisha'               : 'Odisha Gazette', \
'jharkhand'            : 'Jharkhand Gazette', \
'madhyapradesh'        : 'Madhya Pradesh Gazette', \
'punjab'               : 'Punjab Gazette', \
'uttarakhand'          : 'Uttarakhand Gazette', \
'himachal'             : 'Himachal Pradesh Gazette', \
'haryana'              : 'Haryana Gazette', \
'haryanaarchive'       : 'Haryana Gazette', \
'kerala'               : 'Kerala Gazette', \
'stgeorge'             : 'Fort St. George Gazette', \
'keralalibrary'        : 'Kerala Gazette', \
'goa'                  : 'Goa Gazette', \
}

languages = { \
'central_weekly'       : ['eng', 'hin'], \
'central_extraordinary': ['eng', 'hin'], \
'bihar'                : ['eng', 'hin'], \
'delhi_weekly'         : ['eng', 'hin'], \
'delhi_extraordinary'  : ['eng', 'hin'], \
'cgweekly'             : ['eng', 'hin'], \
'cgextraordinary'      : ['eng', 'hin'], \
'andhra'               : ['eng', 'tel'], \
'andhraarchive'        : ['eng', 'tel'], \
'karnataka'            : ['eng', 'kan'], \
'maharashtra'          : ['eng', 'mar'], \
'telangana'            : ['eng', 'tel'], \
'tamilnadu'            : ['eng', 'tam'], \
'odisha'               : ['eng', 'ori'], \
'jharkhand'            : ['eng', 'hin'], \
'madhyapradesh'        : ['eng', 'hin'], \
'punjab'               : ['eng', 'pan'], \
'uttarakhand'          : ['eng', 'hin'], \
'himachal'             : ['eng', 'hin'], \
'haryana'              : ['eng', 'hin'], \
'haryanaarchive'       : ['eng', 'hin'], \
'kerala'               : ['eng', 'mal'], \
'stgeorge'             : ['eng', 'mal'], \
'keralalibrary'        : ['eng', 'mal'], \
'goa'                  : ['eng', 'por'], \
}

srchierarchy = { \
'central'    : ['central_weekly', 'central_extraordinary'], \
'delhi'      : ['delhi_weekly', 'delhi_extraordinary'], \
'chattisgarh': ['cgweekly', 'cgextraordinary'], \
'states'     : ['delhi', 'bihar', 'chattisgarh', 'andhra', 'karnataka', \
                'andhraarchive', 'maharashtra', 'telangana', 'tamilnadu', \
                'odisha', 'jharkhand', 'madhyapradesh', 'punjab', \
                'uttarakhand', 'haryana', 'haryanaarchive', 'kerala', \
                'stgeorge', 'keralalibrary', 'goa'] \
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
