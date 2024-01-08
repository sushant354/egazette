# egazette

This program will download gazettes from various egazette sites
and will place in a specified directory. Gazettes will be
placed into directories named by type and date. If fromdate or
todate is not specified then the default is your current date.

### Modules to be installed:
1. BeautifulSoup4: https://www.crummy.com/software/BeautifulSoup/ https://pypi.org/project/beautifulsoup4/
2. python-magic: https://github.com/ahupp/python-magic https://pypi.org/project/python-magic/
3. pypdf2: https://github.com/mstamy2/PyPDF2 https://pypi.org/project/PyPDF2/
4. Pillow: https://pypi.org/project/Pillow/
5. tesseract: https://github.com/tesseract-ocr/
6. zipfile: https://pypi.org/project/zipp/
7. [For Google Translate API](#for-google-translate-api): \
google-cloud-translate: https://pypi.org/project/google-cloud-translate/
8. For using OCR capabilities: \
google-cloud-vision: https://pypi.org/project/google-cloud-vision/
9. [For Google SpeechToText](#using-google-speechtotext-api): \
google-cloud-speech: https://pypi.org/project/google-cloud-translate/ \
google-cloud-storage: https://pypi.org/project/google-cloud-storage/
10. internetarchive: https://pypi.org/project/internetarchive/

### Usage and available options
```
Usage: python sync.py [-l level(critical, error, warn, info, debug)]
                      [-a (all_downloads)]
                      [-m (updateMeta)]
                      [-n (no aggregation of srcs by hostname)]
                      [-r (updateRaw)]
                      [-f logfile]
                      [-t fromdate (DD-MM-YYYY)] [-T todate (DD-MM-YYYY)]
                      [-s central_weekly -s central_extraordinary -s central
                       -s states 
                       -s andhra -s andhraarchive 
                       -s bihar 
                       -s chattisgarh -s cgweekly -s cgextraordinary 
                       -s delhi -s delhi_weekly -s delhi_extraordinary
                       -s karnataka
                       -s maharashtra -s telangana   -s tamilnadu
                       -s jharkhand   -s odisha      -s madhyapradesh
                       -s punjab      -s uttarakhand -s himachal
                       -s haryana     -s kerala      -s haryanaarchive
                       -s stgeorge    -s himachal    -s keralalibrary
                       ]
                      [-D datadir]
```

### For Google Translate API
```
usage: translate.py [-h] [-t INPUT_TYPE] -l INPUT_LANG -L OUTPUT_LANG -i
                    INPUT_FILE -o OUTPUT_FILE -k KEY_FILE -p PROJECT_ID
                    [-c IGNORE_CLASSES]

       optional arguments:
                    -h, --help            show this help message and exit
                    -t INPUT_TYPE, --type INPUT_TYPE
                                          type of input file(text/sbv/html)
                    -l INPUT_LANG, --input_lang INPUT_LANG
                                          Language of input text
                                          (https://cloud.google.com/translate/docs/languages)
                    -L OUTPUT_LANG        Language of output text
                    -i INPUT_FILE, --infile INPUT_FILE
                                          Input File
                    -o OUTPUT_FILE, --outfile OUTPUT_FILE
                                          Output file
                    -k KEY_FILE, --key KEY_FILE
                                          Google key file
                    -p PROJECT_ID, --project PROJECT_ID
                                          Project ID
                    -c IGNORE_CLASSES, --ignoreclass IGNORE_CLASSES
                                          HTML classes to be ignored for translation
```

### Using Google SpeechToText API
Google SpeechToText API can be used to generate subtitles text as follows:
```
usage: speechtotext.py [-h] [-t OUT_TYPE] [-d DATADIR] [-i INPUT_FILE]
                       [-u GCS_URI] -o OUTPUT_FILE -k KEY_FILE -l LANGCODE
                       [-g LOGLEVEL] [-f LOGFILE] [-b BUCKET_NAME]
                       [-L BUCKET_LOCATION] [-c BUCKET_CLASS] [-w WORD_LIMIT]
                       [-s MAX_SECS]

       optional arguments:
                      -h, --help            show this help message and exit
                      -t OUT_TYPE, --output-type OUT_TYPE
                                            sbv|srt|text
                      -d DATADIR, --data-dir DATADIR
                                            data-dir for caching and intermediate file
                      -i INPUT_FILE, --input INPUT_FILE
                                            filepath to input file
                      -u GCS_URI, --gcs-uri GCS_URI
                                            Google Cloud Storage URI
                      -o OUTPUT_FILE, --output OUTPUT_FILE
                                            filepath to output file
                      -k KEY_FILE, --key KEY_FILE
                                            Google key file
                      -l LANGCODE, --language LANGCODE
                                            language code in BCP-47
                                            (https://cloud.google.com/speech-to-
                                            text/docs/languages)
                      -g LOGLEVEL, --loglevel LOGLEVEL
                                            log level (debug|info|warn|error)
                      -f LOGFILE, --logfile LOGFILE
                                            log file
                      -b BUCKET_NAME, --bucket BUCKET_NAME
                                            bucket name in Gcloud
                      -L BUCKET_LOCATION, --bucket-location BUCKET_LOCATION
                                            bucket location
                      -c BUCKET_CLASS, --bucket-class BUCKET_CLASS
                                            storage class (STANDARD|NEARLINE|COLDLINE|ARCHIVE)
                      -w WORD_LIMIT, --maxwords WORD_LIMIT
                                            max words in a subtitle
                      -s MAX_SECS, --maxseconds MAX_SECS
                                            max duration of a subtitle (seconds)
```
