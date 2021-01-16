import subprocess
import argparse
import logging
import os
import sys
import time
import codecs
import srt
import datetime

from google.cloud import speech
from google.cloud.speech import LongRunningRecognizeResponse

from egazette.tools import gstorage
from egazette.utils.utils import setup_logging

def to_flac(infile, outfile):
    command = ['ffmpeg', '-i', infile, '-ar', '16000', '-vn', '-acodec', 'flac', outfile]
    p = subprocess.Popen(command)
    p.wait()

    returncode = p.returncode
    if returncode == 0:
        return True
    else:
        return False

def get_gcs_uri(bucket_name, blob_name):
   return 'gs://%s/%s' % (bucket_name, blob_name)

def get_google_response(gcs_uri, langcode, cache_file):
    if cache_file and os.path.exists(cache_file):
        serialized = codecs.open(cache_file, 'r', 'utf-8').read()
        response = LongRunningRecognizeResponse()
        return LongRunningRecognizeResponse.from_json(serialized)

    """Asynchronously transcribes the audio file specified by the gcs_uri."""

    client = speech.SpeechClient()

    audio = speech.RecognitionAudio(uri=gcs_uri)
    config = speech.RecognitionConfig(\
        encoding = speech.RecognitionConfig.AudioEncoding.FLAC, \
        sample_rate_hertz  = 16000, \
        enable_automatic_punctuation = True, \
        enable_word_time_offsets = True, \
        language_code = langcode \
    )

    operation = client.long_running_recognize(
        request={"config": config, "audio": audio}
    )

    operation = client.long_running_recognize(config=config, audio=audio)


    while not operation.done():
        logger.info("Waiting for operation to complete for 30 seconds")
        time.sleep(30)

    response = operation.result()
    if not response:
        return None

    if cache_file:
        serialized = LongRunningRecognizeResponse.to_json(response)
        cache_out = codecs.open(cache_file, 'w', 'utf-8')
        cache_out.write(serialized)
        cache_out.close()

    return response 

class Phrase:
    def __init__(self):
        self.wordlist = []
        self.start_ts = None
        self.end_ts   = None
       
    def add_word(self, word):
        self.wordlist.append(word.word)

        if self.start_ts == None:
            self.start_ts = word.start_time

        self.end_ts   = word.end_time

    def get_subtitle(self, index):
        if not self.wordlist:
            return None

        subtitle = srt.Subtitle(index, self.start_ts, self.end_ts, ' '.join(self.wordlist))
        return subtitle 

    def is_within(self, word, word_limit, time_limit):
        if not self.wordlist:
            return True

        if len(self.wordlist) >= word_limit:
            return False

        timedelta = word.end_time - self.start_ts 
        if timedelta > time_limit:
            return False

        return True    

def get_srt_subtitles(response, word_limit, time_limit):
    phrases = []
    for result in response.results:
        phrase  = Phrase()
        phrases.append(phrase)

        for word in result.alternatives[0].words:
           if not phrase.is_within(word, word_limit, time_limit):
                phrase = Phrase()
                phrases.append(phrase)

           phrase.add_word(word)

    transcripts = []
    index       = 0
    for phrase in phrases:
        subtitle = phrase.get_subtitle(index)
        if subtitle:
            transcripts.append(subtitle)
            index += 1
    return srt.compose(transcripts)

def get_arg_parser():
    parser = argparse.ArgumentParser(description='Using Google SpeechToText API to generate subtitles/text')
    parser.add_argument('-t', '--output-type', dest='out_type', action='store',\
                       default = 'srt', help='sbv|srt|text')
    parser.add_argument('-d', '--data-dir', dest='datadir', default='tmp',\
                       action='store', \
                       help='data-dir for caching and intermediate file')
    parser.add_argument('-i', '--input', dest='input_file', action='store',\
                       default=None, help='filepath to input file')
    parser.add_argument('-u', '--gcs-uri', dest='gcs_uri', action='store',\
                       default=None, help='Google Cloud Storage URI')
    parser.add_argument('-o', '--output', dest='output_file', action='store',\
                       required= True, help='filepath to output file')

    parser.add_argument('-k', '--key', dest='key_file', required= True,  \
                         action='store', help='Google key file')

    parser.add_argument('-l', '--language', dest='langcode', required= True,\
                       action='store', \
                       help='language code in BCP-47 (https://cloud.google.com/speech-to-text/docs/languages)')
    parser.add_argument('-g', '--loglevel', dest='loglevel', default='info',\
                       action='store', help='log level (debug|info|warning|error)')
    parser.add_argument('-f', '--logfile', dest='logfile', default= None,\
                        action='store', help='log file')

    parser.add_argument('-b', '--bucket', dest='bucket_name', action='store',\
                        default='speechtotext-indiankanoon', \
                        help='bucket name in Gcloud')
    parser.add_argument('-L', '--bucket-location', dest='bucket_location', \
                        action='store', default='us', help='bucket location')
    parser.add_argument('-c', '--bucket-class', dest='bucket_class', \
                        action='store', default='STANDARD', \
                        help='storage class (STANDARD|NEARLINE|COLDLINE|ARCHIVE)')

    parser.add_argument('-w', '--maxwords', dest='word_limit', type = int, \
                        action='store', default=8, help='max words in a subtitle')
    parser.add_argument('-s', '--maxseconds', dest='max_secs', type = int, \
                        action='store', default = 3, help='max duration of a subtitle (seconds)')
    return parser                      

def process_audio(data_dir, input_file):    
    if not os.path.exists(data_dir):
       os.mkdir(data_dir)
 
    filename = os.path.basename(input_file)
    outfile  = os.path.join(data_dir, filename)
    if os.path.exists(outfile):
        logger = logging.getLogger('speechtotext')                            
        logger.warning('FLAC already exists. Skipping %s', outfile)
    else:
        to_flac(input_file, outfile)

    return outfile 

def upload_audio(audio_file, bucket_name, bucket_class, bucket_location):    
    blob_name = gstorage.upload(bucket_name, bucket_class, \
                                bucket_location, audio_file)
    if not blob_name:                            
        logger = logging.getLogger('speechtotext')                            
        logger.warning('Unable to upload on Gstorage %s ',audio_file)
        return None                  

    return blob_name 

if __name__ == '__main__':
    parser = get_arg_parser()
    args   = parser.parse_args()

    setup_logging(args.loglevel, args.logfile)
    logger = logging.getLogger('speechtotext')                            
    os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = args.key_file

    input_file = args.input_file
    blob_name = None
    if input_file:
        audio_file = process_audio(args.datadir, input_file)
        blob_name = upload_audio(audio_file, args.bucket_name, \
                                args.bucket_class, args.bucket_location)
        gcs_uri = get_gcs_uri(args.bucket_name, blob_name)
    elif args.gcs_uri:
        gcs_uri = args.gcs_uri
        blob_name = gcs_uri.split('/')[-1]
    else:
        logger.error('No media file or gcs_uri specified. Exiting!')
        parser.print_help()
        sys.exit(0)

    cache_file = os.path.join(args.datadir, '%s.json' % blob_name)
    response = get_google_response(gcs_uri, args.langcode, cache_file)
    if args.out_type == 'srt':
        word_limit = args.word_limit
        time_limit =  datetime.timedelta(seconds = args.max_secs)
        subtitles = get_srt_subtitles(response, word_limit, time_limit)
        filehandle = codecs.open(args.output_file, 'w', 'utf8')
        filehandle.write(subtitles)
        filehandle.close()
    else:
       print ('Output type %s not yet supported' % args.out_type, \
              file = sys.stderr)
