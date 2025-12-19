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

def wbsl_identifier(relurl, metainfo):
    bookid = metainfo.get('bookid')
    return bookid

srcinfos = {
    'bis' : {
        'languages' : ['eng'],
        'category'  : 'Bureau of Indian Standards',
    },
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
        'category'  : 'Andhra Pradesh Gazette',
        'enabled'   : False
    },
    'andhra_extraordinary' : {
        'languages' : ['eng', 'tel'],
        'source'    : 'Government of Andhra Pradesh',
        'category'  : 'Andhra Pradesh Extraordinary Gazette'
    },
    'andhra_weekly' : {
        'languages' : ['eng', 'tel'],
        'source'    : 'Government of Andhra Pradesh',
        'category'  : 'Andhra Pradesh Weekly Gazette'
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
        'prefix'    : 'in.gazette.karnataka_new.',
        'enabled'   : False
    },
    'karnataka_daily' : { 
        'languages' : ['eng', 'kan'], 
        'source'    : 'Government of Karnataka',
        'category'  : 'Karnataka Daily Gazette',
        'prefix'    : 'in.gazette.karnataka_d.'
    },
    'karnataka_weekly' : { 
        'languages' : ['eng', 'kan'], 
        'source'    : 'Government of Karnataka',
        'category'  : 'Karnataka Weekly Gazette',
        'prefix'    : 'in.gazette.karnataka_w.'
    },
    'karnataka_extraordinary' : { 
        'languages' : ['eng', 'kan'], 
        'source'    : 'Government of Karnataka',
        'category'  : 'Karnataka ExtraOrdinary Gazette',
        'prefix'    : 'in.gazette.karnataka_eo.'
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
        'identifier_fn': madhyapradesh_identifier
    },
    # 'in.gazette.mizoram.<year>.<id> start_year: 1972 end_year: 2024 count: 9704
    'mizoram'       : {
        'languages' : ['eng', 'lus'],
        'source'    : 'Government of Mizoram',
        'category'  : 'Mizoram Gazette',
        'prefix'    : 'in.gazette.mizoram.',
        'start_date': datetime(1972,1,1)
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
        'start_date': datetime(2014, 1, 1),
        'enabled'   : False
    },
    'uttarakhand_daily' : {
        'languages' : ['eng', 'hin'],
        'source'    : 'Government of Uttarakhand',
        'category'  : 'Uttarakhand Daily Gazette',
        'start_date': datetime(2024, 1, 1)
    },
    'uttarakhand_weekly' : {
        'languages' : ['eng', 'hin'],
        'source'    : 'Government of Uttarakhand',
        'category'  : 'Uttarakhand Weekly Gazette',
        'start_date': datetime(2024, 1, 1)
    },
    'himachal' : {
        'languages' : ['eng', 'hin'],
        'source'    : 'Government of Himachal Pradesh',
        'category'  : 'Himachal Pradesh Gazette',
        'start_date': datetime(2010, 1, 1),
        'list_fields': {
            'notifications': {
                'display_name': 'Notifications',
                'fields': [
                    ('number', 'Number'),
                    ('department', 'Department'), 
                    ('subject', 'Subject')
                ]
            }
        }
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
    },
    
    'rsa' : {
        'languages' : ['eng', 'hin'],
        'source'    : 'Rajasthan State Secretariat',
        'category'  : 'Rajasthan State Archive',
        'prefix'    : 'in.rajastahan.state.archive.'
    },
     # 'in.gazette.manipur.<year>-<month>-<day>.<gznum>' start_date: 2010-04-01 end_date: 2025-11-21
    'manipur'   :  {
        'languages' : ['eng', 'mni'],
        'source'    : 'Government of Manipur',
        'category'  : 'Manipur Gazette',
        'prefix'    : 'in.gazette.manipur.',
        'start_date': datetime(2010,4,1)
    },
    'ladakh' : {
        'languages' : ['eng', 'hin'],
        'source'    : 'Ladakh Administration',
        'category'  : 'Ladakh Gazette',
        'start_date': datetime(2020, 9, 18),
    },
    'chandigarh' : {
        'languages' : ['eng', 'hin'],
        'source'    : 'Chandigarh Administration',
        'category'  : 'Chandigarh Gazette',
        'start_date': datetime(2019, 10, 1),
        'list_fields': {
            'notifications': {
                'display_name': 'Notifications',
                'fields': [
                    ('number', 'Number'),
                    ('department', 'Department'),
                    ('category', 'Category'),
                    ('date', 'Date')
                ]
            }
        }
    },
    'nagaland' : {
        'languages' : ['eng'],
        'source'    : 'Government of Nagaland',
        'category'  : 'Nagaland Gazette',
        'start_date': datetime(2017, 1, 1),
        'enabled'   : False
    },
    'puducherry' : {
        'languages' : ['eng', 'tam', 'fre'],
        'source'    : 'Government of Puducherry',
        'category'  : 'Puducherry Gazette',
        'start_date': datetime(2011, 1, 1),
    },
    'dadranagarhaveli': {
        'languages' : ['eng', 'hin', 'guj'],
        'source'    : 'Dadra And Nagar Haveli And Daman And Diu Administration',
        'category'  : 'Gazette of DNH And DD',
        'start_date': datetime(2021, 1, 1)
    },
    'gujarat' : {
        'languages' : ['eng', 'guj'],
        'source'    : 'Government of Gujarat',
        'category'  : 'Gujarat Gazette',
        'start_date': datetime(1991, 1, 1)
    },
    'jammuandkashmir' : {
        'languages' : ['eng', 'urd'],
        'source'    : 'Government of Jammu and Kashmir',
        'category'  : 'Jammu and Kashmir Gazette',
        'start_date': datetime(2014, 1, 1),
    },
    'andaman' : {
        'languages' : ['eng'], 
        'source'    : 'Andaman and Nicobar Administration',
        'category'  : 'Andaman and Nicobar Gazette',
        'start_date': datetime(1996, 1, 1),
        'enabled'   : False
    },
    'arunachal' : {
        'languages' : ['eng'],
        'source'    : 'Government of Arunachal pradesh',
        'category'  : 'Arunachal Pradesh Gazette',
        #'start_date': datetime(2020, 1, 1),
        'start_date': datetime(2025, 7, 1)
    },
    'assam_extraordinary' : {
        'languages' : ['eng', 'asm'],
        'source'    : 'Government of Assam',
        'category'  : 'Assam Extraordinary Gazette',
        'start_date': datetime(2016, 1, 1)
    },
    'assam_weekly' : {
        'languages' : ['eng', 'asm'],
        'source'    : 'Government of Assam',
        'category'  : 'Assam Weekly Gazette',
        'start_date': datetime(2016, 1, 1)
    },
    'meghalaya' : {
        'languages' : ['eng'],
        'source'    : 'Government of Meghalaya',
        'category'  : 'Meghalaya Gazette',
        'start_date': datetime(2006, 3, 1)
    },
    'tripura_ordinary' : {
        'languages' : ['eng'],
        'source'    : 'Government of Tripura',
        'category'  : 'Tripura Ordinary Gazette',
        # 'start_date': datetime(2018, 1, 1), for the previous verison of the source
        'start_date': datetime(2025, 8, 30)
    },
    'tripura_extraordinary' : {
        'languages' : ['eng'],
        'source'    : 'Government of Tripura',
        'category'  : 'Tripura Extraordinary Gazette',
        # 'start_date': datetime(2018, 1, 1), for the previous verison of the source
        'start_date': datetime(2025, 8, 30)
    },
    'lakshadweep' : {
        'languages' : ['eng', 'hin'],
        'source'    : 'Lakshadweep Administration',
        'category'  : 'Lakshadweep Gazette',
        'start_date': datetime(2016, 1, 1)
    },
    'uttarpradesh_extraordinary' : {
        'languages' : ['eng', 'hin'],
        'source'    : 'Government of Uttar Pradesh',
        'category'  : 'Uttar Pradesh Extraordinary Gazette',
        'start_date': datetime(2018, 12, 21),
    },
    'uttarpradesh_ordinary' : {
        'languages' : ['eng', 'hin'],
        'source'    : 'Government of Uttar Pradesh',
        'category'  : 'Uttar Pradesh Ordinary Gazette',
        'start_date': datetime(2018, 12, 21),
    },
    'sikkim' : {
        'languages' : ['eng'],
        'source'    : 'Government of Sikkim',
        'category'  : 'Sikkim Gazette',
        'start_date': datetime(1975, 9, 8),
    },
    'rajasthan_extraordinary' : {
        'languages' : ['eng', 'hin'],
        'source'    : 'Government of Rajasthan',
        'category'  : 'Rajasthan Extraordinary Gazette',
        'start_date': datetime(2019, 4, 1),
    },
    'rajasthan_ordinary' : {
        'languages' : ['eng', 'hin'],
        'source'    : 'Government of Rajasthan',
        'category'  : 'Rajasthan Ordinary Gazette',
        'start_date': datetime(2019, 4, 1),
    },
    'westbengal' : {
        'languages' : ['eng', 'ben', 'urd'],
        'source'    : 'Government of West Bengal',
        'category'  : 'The Kolkata Gazette',
        'start_date': datetime(1832, 1, 1),
    },
    'wbsl' : {
        'languages' : ['eng', 'ben', 'urd', 'fre', 'ita'],
        'category'  : 'West Bengal Secretariat Library Archive',
        'start_date': datetime(1742, 1, 1),
        'prefix'    : 'wbsl.',
        'identifier_fn': wbsl_identifier,
    },
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


