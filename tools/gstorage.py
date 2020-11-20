import logging
import argparse
import re
import os

from google.cloud import storage

logger = logging.getLogger('storage')

def create_bucket(client, bucket_name, classname, location):
    """Create a new bucket in specific location with storage class"""

    bucket = client.bucket(bucket_name)
    bucket.storage_class = classname
    new_bucket = client.create_bucket(bucket, location = location)

    logger.info("Created bucket %s in %s with storage class %s", \
                new_bucket.name, new_bucket.location, new_bucket.storage_class)
    return new_bucket

def get_bucket(client, bucket_name):
    buckets = client.list_buckets()
    for bucket in buckets:
       if bucket.name == bucket_name:
           return bucket
    return None


def create_bucket_if_notexists(client, bucket_name, classname, location):
    bucket = get_bucket(client, bucket_name)
    if not bucket:
        bucket = create_bucket(client, bucket_name, classname, location)

    return bucket

def get_dest_name(filepath):
    filename =  os.path.basename(filepath)
    dest_name, n = re.subn('[\s.-]+', '-', filename)
    return dest_name

def upload_file(bucket, source_file):
    dest_name = get_dest_name(source_file)
    blob = bucket.get_blob(dest_name)
    if  blob:
        logger.info('Blob already exists. Skipping %s', dest_name)
    else:
        blob = bucket.blob(dest_name)
        blob.upload_from_filename(source_file)
        logger.info('Uploaded %s to %s', source_file, dest_name)
    return dest_name 
    

def delete_blob(bucket, dest_name):
    blob = bucket.blob(dest_name)
    blob.delete()
    logger.info('Deleted %s', dest_name)

def get_arg_parser():
    parser = argparse.ArgumentParser(description='Using Google Storage API to manage objects')

    parser.add_argument('-a', '--action', dest='action', action='store',\
                       default = 'upload', required= True, \
                       help='action - upload|delete')    

    parser.add_argument('-b', '--bucket', dest='bucket_name', action='store',\
                       required= True, help='bucket name')   

    parser.add_argument('-c', '--bucket-class', dest='bucket_class',  \
                       action='store', default='STANDARD', \
                       help='bucket class (STANDARD|NEARLINE|COLDLINE|ARCHIVE)')    
    parser.add_argument('-l', '--bucket-location', dest='bucket_location',  \
                       action='store', default = 'us', \
                       help='bucket location https://cloud.google.com/storage/docs/locations')    

    parser.add_argument('-f', '--filepath', dest='filepath', action='store',\
                       help='File Path')   

    parser.add_argument('-k', '--key', dest='key_file', required= True,  \
                         action='store', help='Google key file')
    parser.add_argument('-n', '--blob-name', dest='blob_name',  \
                         action='store', help='Blob name in the bucket')

    return parser      

def upload(bucket_name, bucket_class, bucket_location, filepath):
    if not filepath or not os.path.exists(filepath) or \
            not os.path.isfile(filepath):
        logger.warn('File does not exist %s', filepath)
        return None

    client = storage.Client()
    bucket = create_bucket_if_notexists(client, bucket_name, bucket_class, \
                                        bucket_location)
    return upload_file(bucket, filepath) 

def delete(bucket_name, blob_name):
    if not blob_name:
        logger.warn('Need to specify blob_name to delete')
        return

    client = storage.Client()
    bucket = get_bucket(client, args.bucket_name)

    if bucket == None:
        logger.warn('Bucket %s does not exist', bucket_name)
        return

    delete_blob(bucket, blob_name)

if __name__ == '__main__':
    parser = get_arg_parser()
    args   = parser.parse_args()

    os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = args.key_file
   
    if args.action == 'upload':
       upload(args.bucket_name, args.bucket_class, args.bucket_location, \
              args.filepath)
    elif args.action == 'delete':
        delete(args.bucket_name, args.blob_name)
