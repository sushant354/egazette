import re
from datetime import datetime

def basic_identifier(relurl, metainfo):
    identifier = relurl.replace('/', '.')
    return identifier

def bihar_identifier(relurl, metainfo):
    dateobj = metainfo.get_date()
    datestr = dateobj.strftime('%Y-%m-%d')
    num = relurl.split('/')[-1]
    return f'{datestr}.{num}'

def madhyapradesh_identifier(relurl, metainfo):
    dateobj = metainfo.get_date()
    datestr = dateobj.strftime('%Y-%m-%d')
    gznum   = metainfo['gznum']
    gztype  = metainfo['gztype']
    return f'{datestr}.{gznum}.{gztype}'

def kerala_identifier(relurl, metainfo):
    identifier = basic_identifier(relurl, metainfo)
    # translation from an earlier cutoff of 80 which included 'kerala_new.' prefix 
    identifier = identifier[:69]
    return identifier

def goa_identifier(relurl, metainfo):
    gznum  = metainfo['gznum']
    series = metainfo['series']
    identifier = f'{gznum}.{series}'
    return identifier

srcinfos = {
    # 'in.gazette.<year>.<id>' start_year: 1922 end_year: 2017 count: 36003
    # 'in.gazette.central_weekly.<year>-<month>-<day>.<id>' start_date: 2018-09-06 end_date: 2018-09-06 count: 1
    # 'in.gazette.central.w.<year>-<month>-<day>.<id>' start_date: 1947-01-01 end_date: 2025-03-08 count: 39285
    'central_weekly' : {
        'languages' : ['eng', 'hin'],
        'source'    : 'Government of India',
        'category'  : 'Weekly Gazette of India',
        'prefix'    : 'in.gazette.central.w.' 
    },
    # 'in.gazette.e.<year>.<id>' start_year: 1929 end_year: 2017 count: 108316
    # 'in.gazette.central.e.<year>-<month>-<day>.<id>' start_date: 1986-01-01 end_date: 2025-03-05 count: 121295
    'central_extraordinary' : {
        'languages' : ['eng', 'hin'], 
        'source'    : 'Government of India',
        'category'  : 'Extrordinary Gazette of India', 
        'prefix'    : 'in.gazette.central.e.' 
    },
    # 'in.gazette.bihar.<year>-<month>-<day>.<id>' start_date: 2017-11-24 end_date: 2018-06-22 count: 724
    # 'in.gov.bih.gazette.<year>.<id>' start_year: 2008 end_year: 2018 count: 9789
    # 'in.gov.bih.gazette.<year>-<month>-<day>.<id>' 2019-01-01 end_year: 2023-05-01 count: 3939
    'bihar' : { 
        'languages' : ['eng', 'hin'], 
        'source'    : 'Government of Bihar',
        'category'  : 'Gazette of Bihar',
        'prefix'    : 'in.gov.bih.gazette.',
        'start_date': datetime(2008, 9, 24),
        'identifier_fn': bihar_identifier
    },
    # 'delhi.egaz.<year>.<month_no_pad>.<day_no_pad>' start_date: 1987-01-01, end_date: 2017-09-08 count: 831
    # 'in.gazette.delhi.w.<year>-<month>-<day>.<id>' start_date: 2011-01-06, end_date: 2025-02-13 count: 627
    'delhi_weekly' : {
        'languages' : ['eng', 'hin'],
        'source'    : 'Government of NCT of Delhi',
        'category'  : 'Delhi Gazette - Weekly',
        'start_date': datetime(2016, 5, 1),
        'prefix'    : 'in.gazette.delhi.w.'
    },
    # 'in.gazette.delhi.e.<year>-<month>-<day>.<id>' start_date: 2011-01-03, end_date: 2025-03-01 count: 3980
    'delhi_extraordinary' : { 
        'languages' : ['eng', 'hin'],
        'source'    : 'Government of NCT of Delhi',
        'category'  : 'Delhi Gazette - Extrordinary',
        'prefix'    : 'in.gazette.delhi.e.'
    },
    # 'in.gazette.chhattisgarh.weekly.<year>-<month>-<day>.<id>' start_date: 2001-07-06 end_date: 2024-08-09 count: 6094
    'cgweekly' : {
        'languages' : ['eng', 'hin'], 
        'source'    : 'Government of Chattisgarh',
        'category'  : 'Chattisgarh Gazette - Weekly',
        'prefix'    : 'in.gazette.chhattisgarh.weekly.',
        'start_date': datetime(2000, 11, 1)
    },
    # 'in.gazette.chhattisgarh.eo.<year>-<month>-<day>.<id>' start_date: 2001-01-04 end_date: 2024-08-08 count: 9193
    'cgextraordinary' : {
        'languages' : ['eng', 'hin'],
        'source'    : 'Government of Chattisgarh',
        'category'  : 'Chattisgarh Gazette - Extrordinary',
        'prefix'    : 'in.gazette.chhattisgarh.eo.'
    },
    # 'in.gazette.andhra.<year>-<month>-<day>.<id>' start_date: 2008-05-22 end_date: 2023-05-03 count: 19184
    'andhra' : {
        'languages' : ['eng', 'tel'],
        'source'    : 'Government of Andhra Pradesh',
        'category'  : 'Andhra Pradesh Gazette'
    },
    'andhraarchive' : { 
        'languages' : ['eng', 'tel'], 
        'source'    : 'Government of Andhra Pradesh',
        'category'  : 'Andhra Pradesh Gazette',
        'enabled'   : False
    },
    # 'in.gov.karn.gaz.<year>.<month>.<date>' start_date: 2003-09-04 end_date: 2017-09-21 count: 684
    # 'in.gazette.karnataka.<year>-<month>-<day>' start_date: 2009-06-11 end_date: 2018-11-01 count: 463
    # 'in.gazette.karnataka_new.<year>-<month>-<day>.<id>' start_date; 2009-06-11 end_date: 2019-12-26 count: 8783
    # 'in.gazette.in.gazette.karnataka_new.<year>-<month>-<day>.<id>' start_date: 2018-10-04, end_date: 2018-10-04 count: 2
    'karnataka' : { 
        'languages' : ['eng', 'kan'], 
        'source'    : 'Government of Karnataka',
        'category'  : 'Karnataka Gazette',
        'prefix'    : 'in.gazette.karnataka_new.'
    },
    # 'in.gazette.maharashtra.<year>-<month>-<day>.<id>' start_date: 2014-01-01 end_date:2023-05-04 count: 17545
    'maharashtra'   : {
        'languages' : ['eng', 'mar'],
        'source'    : 'Government of Maharashtra',
        'category'  : 'Maharashtra Gazette',
        'start_date': datetime(2010, 1, 1)
    },
    # 'in.gazette.telangana.<year>-<month>-<day>.<id>' start_date: 2014-06-02 end_date: 2024-07-15 count: 4338
    'telangana' : {
        'languages' : ['eng', 'tel'],
        'source'    : 'Government of Telangana',
        'category'  : 'Telangana Gazette',
        'start_date': datetime(2014, 1, 1)
    },
    # 'in.gazette.tamilnadu.<year>-<month>-<day>.<id>' start_date: 2008-12-01 end_date: 2025-03-05 count: 13529
    'tamilnadu' : {
        'languages' : ['eng', 'tam'],
        'source'    : 'Government of Tamil Nadu',
        'category'  : 'Tamil Nadu Gazette',
        'start_date': datetime(2008, 1, 1)
    },
    # 'in.gazette.odisha.<year>-<month>-<day>.<id>' start_date: 2004-01-10 end_date: 2020-09-07 count: 22693
    'odisha' : {
        'languages' : ['eng', 'ori'],
        'source'    : 'Government of Odisha',
        'category'  : 'Odisha Gazette'
    },
    # 'in.gazette.jharkhand.<year>-<month>-<day>.<id>' start_date: 2014-01-09 end_date: 2025-02-28 count: count: 8783
    'jharkhand' : {
        'languages' : ['eng', 'hin'],
        'source'    : 'Government of Jharkhand',
        'category'  : 'Jharkhand Gazette'
    },
    # 'in.gazette.madhya.<year>-<month>-<day>.<gznum>.<gztype>' start_date: 2010-01-01 end_date: 2025-03-07 count:8584
    'madhyapradesh' : {
        'languages' : ['eng', 'hin'], 
        'source'    : 'Government of Madhya Pradesh',
        'category'  : 'Madhya Pradesh Gazette',
        'prefix'    : 'in.gazette.madhya.',
        'start_date': datetime(2010, 1, 1),
        'madhyapradesh': madhyapradesh_identifier
    },
    # 'in.gazette.punjab.<year>-<month>-<day>.<id>' start_date; 2016-01-01 end_date: 2020-04-09 count: 2332
    'punjab' : {
        'languages' : ['eng', 'pan'],
        'source'    : 'Government of Punjab',
        'category'  : 'Punjab Gazette',
        'start_date': datetime(2007, 1, 1),
        'enabled'   : False
    },
    # 'in.gazette.punjabdsa.<year>-<month>-<day>.<id>' start_date: 2020-03-20 end_date: 2023-05-03 count: 2612
    'punjabdsa' : {
        'languages' : ['eng', 'pan'],
        'source'    : 'Government of Punjab',
        'category'  : 'Punjab Gazette'
    },
    # 'in.gazette.uttarakhand.<year>-<month>-<day>.<id>' start_date: 2013-01-11 end_date: 2024-06-01 count: 611
    'uttarakhand' : {
        'languages' : ['eng', 'hin'],
        'source'    : 'Government of Uttarakhand',
        'category'  : 'Uttarakhand Gazette',
        'start_date': datetime(2014, 1, 1)
    },
    'himachal' : {
        'languages' : ['eng', 'hin'],
        'source'    : 'Government of Himachal Pradesh',
        'category'  : 'Himachal Pradesh Gazette',
        'start_date': datetime(2010, 1, 1)
    },
    # 'in.gazette.haryana.<year>-<month>-<day>.<id>' start_date: 2014-10-27 end_date: 2025-03-06 count: 14106
    'haryana' : {
        'languages' : ['eng', 'hin'],
        'source'    : 'Government of Haryana',
        'category'  : 'Haryana Gazette',
        'start_date': datetime(2014, 1, 1)
    },
    # 'in.gazette.haryanaarch.<year>-<month>-<day>.<id>' start_date: 1958-12-10 end_date: 2017-12-25 count: 47693
    'haryanaarchive' : {
        'languages' : ['eng', 'hin'],
        'source'    : 'Government of Haryana',
        'category'  : 'Haryana Gazette',
        'start_date': datetime(1958, 1, 1),
        'prefix'    : 'in.gazette.haryanaarch.'
    },
    # 'in.gazette.kerala.<year>-<month>-<day>' start_date: 2007-05-22 end_date: 2018-06-12 count: 552
    # 'in.gazette.kerala_new.<year>-<month>-<day>.<id>' start_date: 2007-05-22 end_date: 2022-02-22 count: 33070
    'kerala' : {
        'languages' : ['eng', 'mal'],
        'source'    : 'Government of Kerala',
        'category'  : 'Kerala Gazette',
        'prefix'    : 'in.gazette.kerala_new.',
        'start_date': datetime(2007, 1, 1),
        'identifier_fn': kerala_identifier
    },
    'keralacompose' : {
        'languages' : ['eng', 'mal'],
        'source'    : 'Government of Kerala',
        'category'  : 'Kerala Gazette',
        'prefix'    : 'in.gazette.keralacompose.',
        'start_date': datetime(2021, 10, 2)
    },
    # 'gazette.stgeorge.TG<year>.TG<year><month_text3_caps><day><type>?' start_date: 1908-07-07 end_date: 1943-02-23 count: 1924
    'stgeorge' : {
        'languages' : ['eng', 'mal'],
        'source'    : 'Madras Presidency',
        'category'  : 'Fort St. George Gazette',
        'prefix'    : 'gazette.stgeorge.',
        'start_date': datetime(1903, 1, 1),
        'enabled'   : False
    },
    # 'gazette.kerala.archive.<year>.<year><month_text3_caps><day><type>?' start_date: 1903-01-06 end_date: 1985-12-31 count: 9489
    'keralalibrary' : {
        'languages' : ['eng', 'mal'],
        'source'    : 'Government of Kerala',
        'category'  : 'Kerala Gazette',
        'prefix'    : 'gazette.kerala.archive.',
        'start_date': datetime(1903, 1, 1),
        'enabled'   : False
    },

    # 'in.gazette.goa.<year>-<month>-<day>.<id>' start_date: 1962-01-25  end_date: 1962-01-25  count: 4
    # 'in.goa.egaz.<gznum>.<series>'  count: 9841
    'goa' : {
        'languages' : ['eng', 'por'],
        'source'    : 'Government of Goa',
        'category'  : 'Goa Gazette',
        'prefix'    : 'in.goa.egaz.',
        'start_date': datetime(1908, 1, 1),
        'identifier_fn': goa_identifier
    },
    # 'in.gazette.csl_weekly.<year>-<month>-<day>.<id>' start_date: 1922-01-28 end_date: 1997-12-29 count: 13855
    'csl_weekly' : { 
        'languages' : ['eng', 'hin'],
        'source'    : 'Government of India', 
        'category'  : 'Weekly Gazette of India',
        'enabled'   : False
    },
    # 'in.gazette.csl_extraordinary.<year>-<month>-<day>.<id>' start_date: 1929-02-28 end_date: 2001-12-03 count: 51465
    'csl_extraordinary' : {
        'languages' : ['eng', 'hin'], 
        'source'    : 'Government of India',
        'category'  : 'Extrordinary Gazette of India',
        'enabled'   : False
    }
}

def get_prefix(srcname):
    srcinfo = srcinfos[srcname]
    prefix = srcinfo.get('prefix', f'in.gazette.{srcname}.')
    return prefix

def get_start_date(srcname):
    srcinfo = srcinfos[srcname]
    start_date = srcinfo.get('start_date', None)
    return start_date

def get_identifier(relurl, metainfo):
    words   = relurl.split('/')
    srcname = words[0]
    relurl  = '/'.join(words[1:])

    relurl, _  = re.subn(r"[',&:%\s;()–]", '', relurl)

    srcinfo = srcinfos[srcname]

    identifier_fn = srcinfo.get('identifier_fn', basic_identifier)

    identifier = identifier_fn(relurl, metainfo)

    prefix = get_prefix(srcname)
    return prefix + identifier


