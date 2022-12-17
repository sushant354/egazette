import logging
import datetime
import re
import calendar

def normalize_date(datestr):
    numlist = re.findall('\d+', datestr)
    if len(numlist) != 3:
        datestr = datestr.strip()
        monthre = 'january|february|march|april|may|june|july|august|september|october|november|december'
        reobj = re.search('(?P<day>\d+)(st|nd|rd|th)?\s+(?P<month>%s)[\s,]+(?P<year>\d+)' % monthre, datestr, flags=re.IGNORECASE)

        if not reobj:
            reobj = re.search('(?P<month>%s)\s+(?P<day>\d+)(st|nd|rd|th)?[\s,]+(?P<year>\d+)'  % monthre, datestr, flags=re.IGNORECASE)

        if reobj:
            groups = reobj.groupdict()
            return dict_to_dateobj({'month': month_to_num(groups['month']), 'day': int(groups['day']), 'year': int(groups['year'])})
        else:
            return None
    else:
        return dict_to_dateobj({'day': int(numlist[1]), 'month': int(numlist[0]), 'year': int(numlist[2])})

def dict_to_dateobj(datedict):
    year  = datedict['year']
    month = datedict['month']
    day   = datedict['day']

    if month > 1800:
        tmp = month
        month = year
        year = tmp

    try:
        dateobj = datetime.date(year, month, day)
    except ValueError as e:
        logger = logging.getLogger('utils')
        logger.warning('Could not get dateobj from: %s, Err: %s' % (datedict,e))
        dateobj = None
    except OverflowError as e:
        logger = logging.getLogger('utils')
        logger.warning('Could not get dateobj from: %s, Err: %s' % (datedict,e))
        dateobj = None

    return dateobj

def month_to_num(month):
    count = 0
    month = month.lower()
    for mth in calendar.month_name:
        if mth.lower() == month:
            return count
        count += 1
    return None

if __name__ == '__main__':
    dateobj = normalize_date('October 3, 2014')
    print (dateobj, type(dateobj))
    dateobj = normalize_date('10/3/2014')
    print (dateobj, type(dateobj))
