from . import central
from . import delhi
from . import bihar
from . import chattisgarh
from . import andhra
from . import karnataka

from . import maharashtra
from . import telangana
from . import tamilnadu

from . import odisha
from . import jharkhand
from . import madhyapradesh

from . import punjab
from . import uttarakhand
from . import haryana

from . import kerala
from . import himachal
from . import mizoram

from . import stgeorge

from . import goa
from . import csl 
from . import bis
from . import rsa
from . import manipur
from . import ladakh
from . import chandigarh
from . import nagaland
from . import puducherry
from . import dadranagarhaveli
from . import gujarat
from . import jammuandkashmir
from . import andaman
from . import arunachal
from . import assam
from . import meghalaya
from . import tripura
from . import lakshadweep
from . import uttarpradesh
from . import sikkim
from . import rajasthan
from . import wbsl
from . import westbengal

from .datasrcs_info import srcinfos

srcdict = { \
'central_weekly'            : central.CentralWeekly, \
'central_extraordinary'     : central.CentralExtraordinary, \
'bihar'                     : bihar.Bihar, \
'delhi_weekly'              : delhi.DelhiWeekly, \
'delhi_extraordinary'       : delhi.DelhiExtraordinary, \
'cgweekly'                  : chattisgarh.ChattisgarhWeekly, \
'cgextraordinary'           : chattisgarh.ChattisgarhExtraordinary, \
'andhra'                    : andhra.Andhra, \
'andhra_extraordinary'      : andhra.AndhraExtraOrdinary, \
'andhra_weekly'             : andhra.AndhraWeekly, \
'andhraarchive'             : andhra.AndhraArchive, \
'karnataka'                 : karnataka.Karnataka, \
'karnataka_extraordinary'   : karnataka.KarnatakaExtraOrdinary, \
'karnataka_weekly'          : karnataka.KarnatakaWeekly, \
'karnataka_daily'           : karnataka.KarnatakaDaily, \
'maharashtra'               : maharashtra.Maharashtra, \
'telangana'                 : telangana.Telangana, \
'tamilnadu'                 : tamilnadu.TamilNadu, \
'odisha'                    : odisha.Odisha, \
'jharkhand'                 : jharkhand.Jharkhand, \
'madhyapradesh'             : madhyapradesh.MadhyaPradesh, \
'punjab'                    : punjab.Punjab, \
'punjabdsa'                 : punjab.PunjabDSA, \
'uttarakhand'               : uttarakhand.Uttarakhand, \
'uttarakhand_daily'         : uttarakhand.UttarakhandDaily, \
'uttarakhand_weekly'        : uttarakhand.UttarakhandWeekly, \
'himachal'                  : himachal.Himachal, \
'haryana'                   : haryana.Haryana, \
'haryanaarchive'            : haryana.HaryanaArchive, \
'kerala'                    : kerala.Kerala, \
'keralacompose'             : kerala.KeralaCompose, \
'stgeorge'                  : stgeorge.StGeorge, \
'keralalibrary'             : stgeorge.KeralaLibrary, \
'goa'                       : goa.Goa, \
'csl_weekly'                : csl.CSLWeekly, \
'csl_extraordinary'         : csl.CSLExtraordinary, \
'bis'                       : bis.BIS, \
'mizoram'                   : mizoram.Mizoram, \
'rsa'                       : rsa.RajasthanStateArchive, \
'manipur'                   : manipur.Manipur, \
'ladakh'                    : ladakh.Ladakh, \
'chandigarh'                : chandigarh.Chandigarh, \
'nagaland'                  : nagaland.Nagaland, \
'puducherry'                : puducherry.Puducherry, \
'dadranagarhaveli'          : dadranagarhaveli.DadraNagarHaveli, \
'gujarat'                   : gujarat.Gujarat, \
'jammuandkashmir'           : jammuandkashmir.JammuAndKashmir, \
'andaman'                   : andaman.Andaman, \
'arunachal'                 : arunachal.Arunachal, \
'assam_extraordinary'       : assam.AssamExtraOrdinary, \
'assam_weekly'              : assam.AssamWeekly, \
'meghalaya'                 : meghalaya.Meghalaya, \
'tripura_ordinary'          : tripura.TripuraOrdinary, \
'tripura_extraordinary'     : tripura.TripuraExtraOrdinary, \
'lakshadweep'               : lakshadweep.Lakshadweep, \
'uttarpradesh_extraordinary': uttarpradesh.UttarPradeshExtraOrdinary, \
'uttarpradesh_ordinary'     : uttarpradesh.UttarPradeshOrdinary, \
'sikkim'                    : sikkim.Sikkim, \
'rajasthan_extraordinary'   : rajasthan.RajasthanExtraOrdinary, \
'rajasthan_ordinary'        : rajasthan.RajasthanOrdinaryCitizen, \
'westbengal'                : westbengal.KolkataWBSL, \
'wbsl'                      : wbsl.WBSL, \
}

srchierarchy = {
    'statutory'     : ['bis'],
    'central'       : ['central_weekly', 'central_extraordinary'],
    'csl'           : ['csl_weekly' , 'csl_extraordinary'],
    'delhi'         : ['delhi_weekly', 'delhi_extraordinary'],
    'chattisgarh'   : ['cgweekly', 'cgextraordinary'],
    'karnataka'     : ['karnataka_daily', 'karnataka_weekly', \
                    'karnataka_extraordinary'],
    'andhra'        : ['andhra_extraordinary', 'andhra_weekly'],
    'uttarakhand'   : ['uttarakhand_daily', 'uttarakhand_weekly'],
    'assam'         : ['assam_extraordinary', 'assam_weekly'],
    'tripura'       : ['tripura_ordinary', 'tripura_extraordinary'],
    'uttarpradesh'  : ['uttarpradesh_extraordinary', 
                       'uttarpradesh_ordinary'],
    'rajasthan'     : ['rajasthan_extraordinary', 'rajasthan_ordinary'],
    'states'        : ['delhi', 'chattisgarh', 'karnataka', 'andhra', \
                       'uttarakhand', 'assam', 'tripura', 'uttarpradesh', \
                       'rajasthan'] + 
                   list(set(srcdict.keys()) -
                        set(['statutory',
                             'central_weekly', 'central_extraordinary',
                             'csl_weekly', 'csl_extraordinary',
                             'delhi_weekly', 'delhi_extraordinary',
                             'cgweekly', 'cgextraordinary'
                             'karnataka_daily', 'karnataka_weekly',
                             'karnataka_extraordinary', 'andhra_weekly',
                             'andhra_extraordinary', 'uttarakhand_daily',
                             'uttarakhand_weekly', 'assam_extraordinary',
                             'assam_weekly', 'tripura_ordinary',
                             'tripura_extraordinary', 'rajasthan_extraordinary',
                             'rajasthan_ordinary', 
                             'uttarpradesh_extraordinary',
                             'uttarpradesh_ordinary']))
}

def get_srcobjs(srclist, storage):
    srcobjs = []

    for src in srclist:
        srcinfo = srcinfos.get(src, {})
        if src in srchierarchy:
            srcobjs.extend(get_srcobjs(srchierarchy[src], storage))            
        if src in srcdict and srcinfo.get('enabled', True):
            obj = srcdict[src](src, storage)
            srcobjs.append(obj)

    return srcobjs
