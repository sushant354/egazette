# egazette
Install BeautifulSoup 4: https://www.crummy.com/software/BeautifulSoup/

Usage:python sync.py   [-l level(critical, error, warn, info, debug)]
                       [-a (all_downloads)]
                       [-m (updateMeta)]
                       [-n (no aggregation of srcs by hostname)]
                       [-r (updateRaw)]
                       [-f logfile]
                       [-t fromdate (DD-MM-YYYY)] [-T todate (DD-MM-YYYY)] 
                       [-D datadir]
                       [-s central_weekly -s central_extraordinary -s central]
The program will download gazettes from various egazette sites
and will place in a specified directory. Gazettes will be
placed into directories named by type and date. If fromdate or
todate is not specified then the default is your current date.

