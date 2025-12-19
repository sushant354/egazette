import os
import urllib.parse
import time
from http.cookiejar import CookieJar

from .westbengal import KolkataWBSL


class WBSL(KolkataWBSL):
    # Language name to ISO 639-3 code mapping
    LANGUAGE_MAP = {
        'English': 'eng',
        'Bengali': 'ben',
        'Urdu': 'urd',
        'Hindi': 'hin',
        'Sanskrit': 'san',
        'Persian': 'fas',
        'Arabic': 'ara',
        'French': 'fre',
        'Italian': 'ita',
    }
    
    def __init__(self, name, storage):
        KolkataWBSL.__init__(self, name, storage)
        self.baseurl = 'https://wbsl.gov.in/eArchive.action'
        self.ajax_url = 'https://wbsl.gov.in/ajaxSearch.action'
        self.calcutta_baseurl = 'https://wbsl.gov.in/getCalcuttaGazette.action'
        self.calcutta_ajax_url = 'https://wbsl.gov.in/ajaxSearch_calcuttaGazette.action'

    def convert_language_to_iso(self, language_name):
        """Convert language name to ISO 639-3 code"""
        if not language_name:
            return None
        
        # Clean up the language name
        language_name = language_name.strip()
        
        # Try direct mapping
        if language_name in self.LANGUAGE_MAP:
            return self.LANGUAGE_MAP[language_name]
        
        # Try case-insensitive mapping
        for name, code in self.LANGUAGE_MAP.items():
            if language_name.lower() == name.lower():
                return code
        
        # Log unknown language
        self.logger.warning('Unknown language name: %s, using as-is', language_name)
        return language_name.lower()[:3]  # Return first 3 chars as fallback
    
    def parse_result(self, entry):
        """Override to convert language to ISO code and add description"""
        # Call parent's parse_result
        metainfo = super().parse_result(entry)
        if not metainfo:
            return None
        
        # Convert language to ISO 639-3 code
        if 'language' in metainfo:
            language_name = metainfo['language']
            iso_code = self.convert_language_to_iso(language_name)
            if iso_code:
                metainfo['language'] = iso_code
                self.logger.debug('Converted language "%s" to ISO code "%s"', 
                                language_name, iso_code)
        
        # Add description if available in entry
        if entry.get('description'):
            metainfo['description'] = entry.get('description').strip()
        
        # Add bookheadno if available and not N.A.
        if entry.get('bookheadno') and entry.get('bookheadno') != 'N.A.':
            metainfo['bookheadno'] = entry.get('bookheadno').strip()
        
        return metainfo
    
    def save_gazette(self, relurl, gurl, metainfo, postdata=None, referer=None, 
                     cookiefile=None, validurl=True, min_size=0, count=0, 
                     hdrs={}, encodepost=True):
        """Override to use source_url instead of url"""
        # Set source_url before calling parent
        if validurl:
            metainfo['source_url'] = self.url_fix(gurl)
        
        # Call parent without setting url
        return super().save_gazette(relurl, gurl, metainfo, postdata=postdata, 
                                   referer=referer, cookiefile=cookiefile, 
                                   validurl=False, min_size=min_size, 
                                   count=count, hdrs=hdrs, encodepost=encodepost)

    def get_calcutta_cache_file(self):
        """Get path to cached Calcutta Gazette list"""
        basedir = os.path.dirname(self.storage_manager.rawdir)
        cache_dir = os.path.join(basedir, 'temp', self.name, 'calcutta_cache')
        os.makedirs(cache_dir, exist_ok=True)
        return os.path.join(cache_dir, 'calcutta_bookids.json')

    def load_calcutta_bookids_cache(self):
        """Load Calcutta bookids from cache if available"""
        cache_file = self.get_calcutta_cache_file()
        
        if not os.path.exists(cache_file):
            return None
        
        try:
            import json
            with open(cache_file, 'r') as f:
                bookids_list = json.load(f)
            
            calcutta_bookids = set(bookids_list)
            self.logger.info('Loaded %d Calcutta bookids from cache', len(calcutta_bookids))
            return calcutta_bookids
        except Exception as e:
            self.logger.warning('Could not load Calcutta cache: %s', e)
            return None

    def save_calcutta_bookids_cache(self, calcutta_bookids):
        """Save Calcutta bookids to cache"""
        cache_file = self.get_calcutta_cache_file()
        
        try:
            import json
            with open(cache_file, 'w') as f:
                json.dump(list(calcutta_bookids), f, indent=2)
            self.logger.info('Cached %d Calcutta bookids to %s', len(calcutta_bookids), cache_file)
        except Exception as e:
            self.logger.warning('Could not save Calcutta cache: %s', e)

    def get_calcutta_bookids(self, cookiejar, event):
        """Fetch all bookids from Calcutta Gazette to filter them out"""
        # Try to load from cache first
        calcutta_bookids = self.load_calcutta_bookids_cache()
        if calcutta_bookids is not None:
            return calcutta_bookids
        
        self.logger.info('Fetching Calcutta Gazette bookids for filtering...')
        
        calcutta_bookids = set()
        offset = 0
        page_size = 100
        
        # Visit Calcutta Gazette page first to establish session
        response = self.download_url(self.calcutta_baseurl, loadcookies=cookiejar, savecookies=cookiejar)
        if not response or not response.webpage:
            self.logger.warning('Could not establish session at Calcutta Gazette page')
            return calcutta_bookids
        
        while True:
            if event.is_set():
                self.logger.warning('Exiting prematurely as timer event is set')
                break
            
            self.logger.info('Fetching Calcutta Gazette list at offset %d', offset)
            
            # Build AJAX URL for Calcutta Gazette
            params = {
                'sEcho': '1',
                'iColumns': '2',
                'sColumns': ',',
                'iDisplayStart': str(offset),
                'iDisplayLength': str(page_size),
                'mDataProp_0': '',
                'sSearch_0': '',
                'bRegex_0': 'false',
                'bSearchable_0': 'true',
                'bSortable_0': 'true',
                'mDataProp_1': '',
                'sSearch_1': '',
                'bRegex_1': 'false',
                'bSearchable_1': 'true',
                'bSortable_1': 'true',
                'sSearch': '',
                'bRegex': 'false',
                'iSortCol_0': '0',
                'sSortDir_0': 'asc',
                'iSortingCols': '1',
                '_': str(int(time.time() * 1000))
            }
            
            url = self.calcutta_ajax_url + '?' + urllib.parse.urlencode(params)
            
            response = self.download_url(url, loadcookies=cookiejar, savecookies=cookiejar, referer=self.calcutta_baseurl)
            if not response or not response.webpage:
                self.logger.warning('Could not fetch Calcutta Gazette list at offset %d', offset)
                break
            
            try:
                import json
                data = json.loads(response.webpage.decode('utf-8'))
            except Exception as e:
                self.logger.warning('Could not parse JSON response: %s', e)
                break
            
            if not data or not data.get('data'):
                break
            
            entries = data.get('data', [])
            for entry in entries:
                bookid = str(entry.get('bookid'))
                if bookid:
                    calcutta_bookids.add(bookid)
            
            total_records = data.get('iTotalRecords', 0)
            self.logger.info('Fetched %d Calcutta entries, total available: %d', len(entries), total_records)
            
            if offset + len(entries) >= total_records:
                break
            
            offset += page_size
        
        self.logger.info('Found %d bookids in Calcutta Gazette to filter out', len(calcutta_bookids))
        
        # Save to cache
        if calcutta_bookids:
            self.save_calcutta_bookids_cache(calcutta_bookids)
        
        return calcutta_bookids

    def sync(self, fromdate, todate, event):
        dls = []
        
        fromdate  = fromdate.date()
        todate    = todate.date()
        from_year = fromdate.year
        to_year   = todate.year
        
        self.logger.info('Syncing from %s to %s (years %d-%d)', 
                         fromdate, todate, from_year, to_year)
        
        # Establish session by visiting main page first
        cookiejar = CookieJar()
        
        response = self.download_url(self.baseurl, savecookies=cookiejar)
        if not response or not response.webpage:
            self.logger.warning('Could not establish session at %s', self.baseurl)
            return dls
        
        curr_url = response.response_url
        self.logger.info('Session established, cookies: %d', len(cookiejar))
        
        # Get Calcutta Gazette bookids to filter out
        calcutta_bookids = self.get_calcutta_bookids(cookiejar, event)

        # add a known problematic book to ignore
        # calcutta_bookids.add('8951')
        
        # Parse all gazette entries from eArchive (from cache or server)
        all_entries = self.get_results(cookiejar, curr_url, event)
        
        # Filter out entries that are in Calcutta Gazette
        filtered_entries = []
        for entry in all_entries:
            bookid = str(entry.get('bookid'))
            if bookid not in calcutta_bookids:
                filtered_entries.append(entry)
            else:
                self.logger.debug('Filtering out bookid %s (in Calcutta Gazette)', bookid)
        
        self.logger.info('Filtered %d entries to %d (removed %d Calcutta Gazette entries)',
                        len(all_entries), len(filtered_entries), len(all_entries) - len(filtered_entries))
        
        # Convert entries to metainfos
        metainfos = []
        for entry in filtered_entries:
            metainfo = self.parse_result(entry)
            if metainfo:
                metainfos.append(metainfo)
        
        self.logger.info('Extracted %d metainfos from %d entries', len(metainfos), len(filtered_entries))
        
        # Download based on metainfos
        self.download_metainfos(dls, metainfos, from_year, to_year, event)
        
        self.logger.info(f'Got {len(dls)} Gazettes from {fromdate} to {todate}')

        return dls
