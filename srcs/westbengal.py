import os
import urllib.parse
import ssl
import re
import json
import time
import warnings
import shutil
from http.cookiejar import CookieJar

import pymupdf

from .basegazette import BaseGazette
from ..utils import utils


# Create custom SSL context to handle weak DH key on wbsl.gov.in
warnings.filterwarnings('ignore', message='.*unverified.*')

def create_weak_ssl_context():
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    # Use ciphers that exclude DH to avoid DH_KEY_TOO_SMALL error
    ctx.set_ciphers('HIGH:!DH:!aNULL')
    return ctx

ssl._create_default_https_context = create_weak_ssl_context


class KolkataWBSL(BaseGazette):
    def __init__(self, name, storage):
        BaseGazette.__init__(self, name, storage)
        self.baseurl = 'https://wbsl.gov.in/getCalcuttaGazette.action'
        self.ajax_url = 'https://wbsl.gov.in/ajaxSearch_calcuttaGazette.action'
        self.bookreader_url = 'https://wbsl.gov.in/bookReader.action'
        self.hostname = 'wbsl.gov.in'

    def get_session(self):
        # Override to disable SSL verification (weak DH key on wbsl.gov.in)
        s = super().get_session()
        s.verify = False
        return s

    def extract_year_from_text(self, text):
        """Extract year from any text field"""
        if not text:
            return None
        # Look for 4-digit year in text
        year_patterns = [
            r'\b(1[89]\d{2})\b',  # 1800-1999
            r'\b(20[0-2]\d)\b',   # 2000-2029
        ]
        
        for pattern in year_patterns:
            match = re.search(pattern, text)
            if match:
                year = int(match.group(1))
                if 1800 <= year <= 2100:
                    return year
        
        return None

    def extract_year_from_title(self, title):
        """Deprecated: use extract_year_from_text instead"""
        return self.extract_year_from_text(title)

    def parse_result(self, entry):
        metainfo = utils.MetaInfo()
        
        title = entry.get('title', '').strip()
        
        # Get year - try multiple sources in order of preference
        year_str = entry.get('copyrightdate', '0000')
        try:
            year = int(year_str)
            if year < 1800 or year > 2100:
                year = None
        except (ValueError, TypeError):
            year = None
        
        # If copyrightdate is invalid, try extracting from title and filename
        if year is None:
            year = self.extract_year_from_text(title)
            if year is None:
                year = self.extract_year_from_text(entry.get('filename', ''))

        if year is None:
            self.logger.warning('Could not extract valid year from: %s', title)
        else:
            metainfo['year'] = year
        
        # Store the original book title
        metainfo['title'] = title
        metainfo['bookid'] = str(entry.get('bookid'))
        
        if entry.get('publisher') and entry.get('publisher') != 'N.A.':
            metainfo['publisher'] = entry.get('publisher')
        
        if entry.get('creator') and entry.get('creator') != 'N.A.':
            metainfo['creator'] = entry.get('creator')
        
        if entry.get('language'):
            metainfo['language'] = entry.get('language')
        
        # Set gazette type (only for non-main types)
        title_lower = title.lower()
        if 'extraordinary' in title_lower or 'extra ordinary' in title_lower:
            metainfo.set_gztype('Extraordinary')
        elif 'index' in title_lower:
            metainfo.set_gztype('Index')
        elif 'supplement' in title_lower:
            metainfo.set_gztype('Supplement')
        elif 'appendix' in title_lower:
            metainfo.set_gztype('Appendix')
        # Don't set gztype for main/regular gazettes
        
        # Add subject information
        subjects = []
        for i in range(3):
            subj_key = 'subject' if i == 0 else f'subject{i}'
            if entry.get(subj_key):
                subjects.append(entry.get(subj_key))
        if subjects:
            metainfo['subject'] = ', '.join(subjects)
        
        # Add keywords - split by capital letters for readability
        if entry.get('keywords'):
            keywords_raw = entry.get('keywords')
            # Split concatenated keywords by capital letters
            # e.g., "LegislativeDepartmentEastIndianRailway" -> "Legislative Department, East Indian Railway"
            keywords_split = re.sub(r'([a-z])([A-Z])', r'\1, \2', keywords_raw)
            metainfo['keywords'] = keywords_split
        
        # Add disk name for reference
        if entry.get('disk_name'):
            metainfo['disk_name'] = entry.get('disk_name')
        
        if entry.get('filename'):
            metainfo['filename'] = entry.get('filename')
        
        return metainfo

    def get_gazette_list_cache_file(self):
        """Get path to cached gazette list"""
        # Use storage manager's base directory
        basedir = os.path.dirname(self.storage_manager.rawdir)
        cache_dir = os.path.join(basedir, 'temp', self.name, 'wbsl_cache')
        os.makedirs(cache_dir, exist_ok=True)
        return os.path.join(cache_dir, 'gazette_list.json')

    def load_cached_gazette_list(self):
        """Load gazette list from cache if available"""
        cache_file = self.get_gazette_list_cache_file()
        
        if not os.path.exists(cache_file):
            return None
        
        try:
            with open(cache_file, 'r') as f:
                cached_data = json.load(f)
            
            self.logger.info('Loaded %d gazette entries from cache', len(cached_data))
            return cached_data
        except Exception as e:
            self.logger.warning('Could not load cache: %s', e)
            return None

    def save_gazette_list_cache(self, gazette_list):
        """Save gazette list to cache"""
        cache_file = self.get_gazette_list_cache_file()
        
        try:
            with open(cache_file, 'w') as f:
                json.dump(gazette_list, f, indent=2)
            self.logger.info('Cached %d gazette entries to %s', len(gazette_list), cache_file)
        except Exception as e:
            self.logger.warning('Could not save cache: %s', e)

    def fetch_gazette_list_with_session(self, display_start, display_length, cookiejar, referer):
        """Fetch gazette list from AJAX endpoint with session cookies"""
        params = {
            'sEcho': '1',
            'iColumns': '2',
            'sColumns': ',',
            'iDisplayStart': str(display_start),
            'iDisplayLength': str(display_length),
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
            '_': str(int(time.time() * 1000))  # Timestamp in milliseconds
        }
        
        # AJAX endpoint uses GET with query parameters
        url = self.ajax_url + '?' + urllib.parse.urlencode(params)
        
        response = self.download_url(url, loadcookies=cookiejar, savecookies=cookiejar, referer=referer)
        if not response or not response.webpage:
            self.logger.warning('Could not fetch gazette list at offset %d', display_start)
            return None
        
        try:
            data = json.loads(response.webpage.decode('utf-8'))
            return data
        except Exception as e:
            self.logger.warning('Could not parse JSON response: %s', e)
            return None

    def fetch_gazette_list(self, display_start=0, display_length=100):
        """Fetch gazette list from AJAX endpoint"""
        params = {
            'sEcho': '1',
            'iColumns': '2',
            'sColumns': ',',
            'iDisplayStart': str(display_start),
            'iDisplayLength': str(display_length),
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
            '_': str(int(time.time() * 1000))  # Timestamp in milliseconds
        }
        
        # AJAX endpoint uses GET with query parameters
        url = self.ajax_url + '?' + urllib.parse.urlencode(params)
        
        response = self.download_url(url)
        if not response or not response.webpage:
            self.logger.warning('Could not fetch gazette list at offset %d', display_start)
            return None
        
        try:
            data = json.loads(response.webpage.decode('utf-8'))
            return data
        except Exception as e:
            self.logger.warning('Could not parse JSON response: %s', e)
            return None

    def get_image_cache_dir(self, bookid):
        """Get persistent cache directory for book images"""
        # Use storage manager's base directory
        basedir = os.path.dirname(self.storage_manager.rawdir)
        cache_base = os.path.join(basedir, 'temp', self.name, 'wbsl_images')
        os.makedirs(cache_base, exist_ok=True)
        
        book_cache = os.path.join(cache_base, str(bookid))
        os.makedirs(book_cache, exist_ok=True)
        
        return book_cache

    def download_bookreader_page(self, bookid):
        """Download the book reader page to extract total pages and image path"""
        # Check cache first
        image_dir = self.get_image_cache_dir(bookid)
        cache_file = os.path.join(image_dir, 'bookreader_info.json')
        
        if os.path.exists(cache_file):
            try:
                with open(cache_file, 'r') as f:
                    cached_info = json.load(f)
                self.logger.info('Using cached book reader info for bookid %s', bookid)
                return cached_info
            except Exception as e:
                self.logger.warning('Could not read cached info: %s', e)
        
        url = f'{self.bookreader_url}?bookId={bookid}'
        
        response = self.download_url(url)
        if not response or not response.webpage:
            self.logger.warning('Could not fetch book reader page for bookid %s', bookid)
            return None
        
        try:
            content = response.webpage.decode('utf-8')
        except Exception:
            content = response.webpage.decode('latin-1')
        
        # Extract total pages
        totalpages_match = re.search(r"var totalpages = '(\d+)'", content)
        if not totalpages_match:
            self.logger.warning('Could not find total pages for bookid %s', bookid)
            return None
        
        total_pages = int(totalpages_match.group(1))
        
        # Extract variables from JavaScript - these are more reliable than parsing HTML
        disk_match = re.search(r"var disk_name = '([^']+)'", content)
        filename_match = re.search(r"var filename = '([^']+)'", content)
        
        if not disk_match or not filename_match:
            self.logger.warning('Could not find disk_name or filename for bookid %s', bookid)
            return None
        
        disk_name = disk_match.group(1)
        title_path = filename_match.group(1)
        
        book_info = {
            'total_pages': total_pages,
            'disk_name': disk_name,
            'title_path': title_path
        }
        
        # Cache the info
        try:
            with open(cache_file, 'w') as f:
                json.dump(book_info, f, indent=2)
            self.logger.info('Cached book reader info for bookid %s', bookid)
        except Exception as e:
            self.logger.warning('Could not cache book reader info: %s', e)
        
        return book_info

    def create_pdf_from_images(self, image_dir):
        """Create a PDF from images in a directory"""
        # Get list of image files sorted by name
        image_files = sorted([f for f in os.listdir(image_dir) if f.endswith('.jpg')])
        
        if not image_files:
            self.logger.warning('No images found in %s', image_dir)
            return None
        
        self.logger.info('Creating PDF from %d images', len(image_files))
        pdf_doc = pymupdf.open()
        
        for idx, img_file in enumerate(image_files):
            if idx % 50 == 0:
                self.logger.info('Adding image %d/%d to PDF', idx + 1, len(image_files))
            
            img_path = os.path.join(image_dir, img_file)
            try:
                # Open the image to get dimensions
                img = pymupdf.open(img_path)
                pdfbytes = img.convert_to_pdf()
                img.close()
                
                # Open the single-page PDF and insert it
                imgpdf = pymupdf.open("pdf", pdfbytes)
                pdf_doc.insert_pdf(imgpdf)
                imgpdf.close()
            except Exception as e:
                self.logger.warning('Could not add image %s to PDF: %s', img_file, e)
                continue
        
        # Save to bytes
        pdf_bytes = pdf_doc.tobytes()
        pdf_doc.close()
        
        return pdf_bytes

    def pull_gazette(self, gurl, referer=None, postdata=None, cookiefile=None, 
                     headers={}, encodepost=True):
        """
        Override pull_gazette to handle WBSL book reader downloads.
        gurl is expected to be the book reader URL: bookReader.action?bookId={bookid}
        """
        # Extract bookid from URL
        bookid_match = re.search(r'bookId=(\d+)', gurl)
        if not bookid_match:
            self.logger.warning('Could not extract bookid from URL: %s', gurl)
            return None
        
        bookid = bookid_match.group(1)
        
        # Get book reader page info
        self.logger.info('Fetching book reader page for bookid %s', bookid)
        book_info = self.download_bookreader_page(bookid)
        if not book_info:
            return None
        
        total_pages = book_info['total_pages']
        disk_name = book_info['disk_name']
        title_path = book_info['title_path']
        
        self.logger.info('Book has %d pages', total_pages)
        
        # Get persistent image cache directory
        image_dir = self.get_image_cache_dir(bookid)
        self.logger.info('Using image cache directory: %s', image_dir)
        
        # Build image URLs and download all pages
        # URL-encode the title_path to handle special characters like apostrophes, commas, spaces
        title_path = title_path.replace("&#039;", "'")
        base_url = f'https://wbsl.gov.in/Books/{disk_name}/{title_path}/PTIFF/'
        
        for page_num in range(1, total_pages + 1):
            page_str = str(page_num).zfill(8)
            img_path = os.path.join(image_dir, f'{page_str}.jpg')
            
            # Skip if already downloaded
            if os.path.exists(img_path):
                if page_num % 100 == 0:
                    self.logger.info('Page %d/%d already cached', page_num, total_pages)
                continue
            
            if page_num % 50 == 0 or page_num == 1:
                self.logger.info('Downloading page %d/%d', page_num, total_pages)
            
            img_url = f'{base_url}{page_str}.jpg'
            
            response = self.download_url(img_url)
            if not response or not response.webpage:
                self.logger.warning('Could not download page %d from %s', page_num, img_url)
                continue
            
            # Save image to cache directory
            with open(img_path, 'wb') as f:
                f.write(response.webpage)
        
        # Verify all pages were downloaded
        downloaded_images = sorted([f for f in os.listdir(image_dir) if f.endswith('.jpg')])
        self.logger.info('Downloaded %d/%d pages', len(downloaded_images), total_pages)
        
        if len(downloaded_images) < total_pages * 0.95:  # Allow 5% missing pages
            self.logger.warning('Only %d/%d pages downloaded successfully', len(downloaded_images), total_pages)
        
        # Create PDF from all images
        self.logger.info('Creating PDF from downloaded images...')
        pdf_bytes = self.create_pdf_from_images(image_dir)
        
        if not pdf_bytes:
            return None
        
        # Create a WebResponse object to return
        from .basegazette import WebResponse
        web_response = WebResponse()
        web_response.set_webpage(pdf_bytes)
        web_response.set_srvresponse({'headers': {'content-type': 'application/pdf'}, 'status': 200})
        web_response.set_response_url(gurl)
        
        self.logger.info('Successfully created PDF (%d bytes) from %d pages', len(pdf_bytes), total_pages)
        
        # Clean up image cache after successful PDF creation
        try:
            shutil.rmtree(image_dir)
            self.logger.info('Cleaned up image cache %s', image_dir)
        except Exception as e:
            self.logger.warning('Could not clean up image cache %s: %s', image_dir, e)
        
        return web_response

    def get_results(self, cookiejar, curr_url, event):
        """Parse all gazette entries from cache or by fetching from server"""
        # Try to load from cache first
        all_entries = self.load_cached_gazette_list()
        
        if all_entries is None:
            # Fetch all gazette entries with pagination
            all_entries = []
            offset = 0
            page_size = 100
            
            while True:
                if event.is_set():
                    self.logger.warning('Exiting prematurely as timer event is set')
                    break
                
                self.logger.info('Fetching gazette list at offset %d', offset)
                data = self.fetch_gazette_list_with_session(offset, page_size, cookiejar, curr_url)
                
                if not data or not data.get('data'):
                    break
                
                entries = data.get('data', [])
                all_entries.extend(entries)
                
                total_records = data.get('iTotalRecords', 0)
                self.logger.info('Fetched %d entries, total available: %d', len(entries), total_records)
                
                if offset + len(entries) >= total_records:
                    break
                
                offset += page_size
            
            self.logger.info('Fetched %d total gazette entries', len(all_entries))
            
            # Save to cache
            if all_entries:
                self.save_gazette_list_cache(all_entries)
        
        return all_entries

    def download_metainfos(self, dls, metainfos, from_year, to_year, event):
        """Download gazettes based on metainfo list"""
        
        for metainfo in metainfos:
            if event.is_set():
                self.logger.warning('Exiting prematurely as timer event is set')
                return
            
            gazette_year = metainfo.get('year')
            
            # Filter by year range (allow None to pass when from_year is 1500)
            if gazette_year is not None and (gazette_year < from_year or gazette_year > to_year):
                continue
            
            bookid = metainfo['bookid']
            title = metainfo['title']
            
            self.logger.info('Processing: [%s] %s (Year %s)', bookid, title[:60], gazette_year or 'Unknown')
            
            # Construct the book reader URL
            gzurl = f'{self.bookreader_url}?bookId={bookid}'
            
            # Construct the relative path using year and bookid
            # Final IA identifier will be: in.gazette.westbengal_wbsl.<year>.<bookid>
            relpath = os.path.join(self.name, str(gazette_year))
            relurl = os.path.join(relpath, bookid)
            
            # Use save_gazette which handles all the checks
            if self.save_gazette(relurl, gzurl, metainfo):
                dls.append(relurl)
        

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
        
        # Parse all gazette entries (from cache or server)
        all_entries = self.get_results(cookiejar, curr_url, event)
        
        # Convert entries to metainfos
        metainfos = []
        for entry in all_entries:
            metainfo = self.parse_result(entry)
            if metainfo:
                metainfos.append(metainfo)
        
        self.logger.info('Extracted %d metainfos from %d entries', len(metainfos), len(all_entries))
        
        # Download based on metainfos
        self.download_metainfos(dls, metainfos, from_year, to_year, event)
        
        self.logger.info(f'Got {len(dls)} Gazettes from {fromdate} to {todate}')

        return dls