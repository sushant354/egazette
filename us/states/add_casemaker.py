import csv
import datetime
import os
import logging
import re
import tarfile
import logging

from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import UploadedFile
from django.core.management.base import BaseCommand

from internetarchive import download
from indigo.plugins import plugins
from indigo_api.models import Document, Language, Task, Work, Country, Locality, Commencement

class Command(BaseCommand):
    help = 'Imports new casemaker files.' \
           'Example: python manage.py add_casemaker --item <internetarchive-item> --destdir <data-dir-for-processing> --globpattern <glob-pattern-for-item-selection>'

    def add_arguments(self, parser):
        parser.add_argument('-i', '--item', dest= 'item', action='store', \
                            help = 'item on internet-archive')
        parser.add_argument('-d', '--destdir', dest= 'destdir', action='store',\
                            help = 'dest dir for processing')
        parser.add_argument('-g', '--globpattern', dest= 'globpattern', \
                           action='store', help = 'glob pattern for selecting files in an internetarchive item')

    def create_review_task(self, document, user):
        task = Task()
        task.title = 'Review batch-imported document'
        task.description = '''
        This document was imported as part of a batch.
        - Double-check that the content is on the right work and at the right point in time.
        - Clean up any import errors as with a normal import.
        '''
        task.country = document.work.country
        task.locality = document.work.locality
        task.work = document.work
        task.document = document
        task.created_by_user = user
        task.save()

    def import_akn_file(self, user, work, date, language, aknfile):
        document = Document()
        document.document_xml = aknfile
        document.work = work
        document.expression_date = date
        document.language = language
        document.created_by_user = user
        document.draft = False
        document.updated_by_user = user
        document.save_with_revision(user)
        #self.create_review_task(document, user)

    def get_frbr_uri(self, country, locality, actyear, actnum, doctype):
        if doctype == 'act':
            frbr_uri = '/akn/%s-%s/act/%s/%s' % (country, locality, actyear, actnum)
        else:    
            frbr_uri = '/akn/%s-%s/act/%s/%s/%s' % (country, locality, doctype, actyear, actnum)
        return frbr_uri   

    def add_file(self, country, locality, actyear, actnum, doctype, aknfile):
        country  = Country.objects.get(country_id =  country_name)
        locality = Locality.objects.get(code = locality_name, \
                                        country = country)

        language = Language.objects.get(language_id='en')            

        frbr_uri = self.get_frbr_uri(country, locality, actyear, actnum, doctype)
        work = self.create_work(user, frbr_uri, row['title'], \
                                publishdate, country, locality)
        if work == None:
            print('Could not add the work:', frbr_uri)
            return 
                                    
        self.import_akn_file(user, work, publishdate, language, aknfile)  

    def get_work(self, frbr_uri):
        try:
            work = Work.objects.get(frbr_uri=frbr_uri)
        except Work.DoesNotExist:
            return None
        return work

    def create_commencement(self, work, user, publishdate):
        Commencement.objects.get_or_create(
            commenced_work=work,
            commencing_work=None,
            date=publishdate,
            defaults={
                'main': True,
                'all_provisions': True,
                'created_by_user': user,
            },
        )
   
    def create_work(self, user, frbr_uri, title, publishdate, country, locality):

        work = Work()

        work.frbr_uri  = frbr_uri
        work.country   = country
        work.locality  = locality 
        work.title     = title
        work.commenced = True

        work.created_by_user  = user
        work.updated_by_user  = user
        work.publication_date = publishdate

        try:
            work.full_clean()
            work.save_with_revision(user)
        except ValidationError as e:
            logger = logging.getLogger('import.bareacts')
            logger.warning('Error in adding work for %s: %s', frbr_uri, e)
            return None

        self.create_commencement(work, user, publishdate)
        return work

    def get_user(self):
        return User.objects.get(id=1)

        for user in User.objects.all().order_by('id'):
            print('{}: {} {}'.format(user.id, user.first_name, user.last_name))
        while True:
            try:
                result = int(eval(input('Which user are you? Select the number from the list above: ')))
                user = User.objects.get(id=result)
            except:
                print('\nSomething went wrong; try again (you must type a number from the list above)\n\n')
            else:
                print('\nUser selected: {} {}.\n\n'.format(user.first_name, user.last_name))
                return user

    def handle(self, *args, **options):
        self.logger  = logging.getLogger('casemaker')
        item         = options['item']
        destdir      = options['destdir']
        glob_pattern = options['globpattern']

        self.download_item(item, glob_pattern, destdir)

        user = self.get_user()
        dirpath = os.path.join(destdir, item)
        self.process_recursive(user, dirpath)

    def process_recursive(self, user, dirpath):    
        for filename in os.listdir(dirpath):
            filepath = os.path.join(dirpath, filename)
            if os.path.isdir(filepath):
                self.process_recursive(user, filepath)
            elif re.search('\.tar$', filepath):
                self.process_state(user, filepath)

    def find_xml_dir(self, dirpath):
        for filename in os.listdir(dirpath):
            filepath = os.path.join(dirpath, filename)
            if os.path.isdir(filepath):
                if filename == 'XML':
                    return filepath
                else:
                    return self.find_xml_dir(filepath)
        return None           

    def process_state(self, user, filepath):
         f = tarfile.open (filepath)
         outpath = re.sub('.tar$', '', filepath)
         f.extractall(outpath)
         xmldir = self.find_xml_dir(outpath)
         if not xmldir:
             self.logger.warn('No XML directory found in %s', outpath)
             return

         for filename in os.listdir(xmldir):
             xmlpath = os.path.join(xmldir, filename)
             if not os.path.isdir(xmlpath):
                 self.process_xml_file(xmlpath)

    def process_xml_file(self, xmlpath):
        print (xmlpath)
    def download_item(self, item, glob_pattern, destdir):
        success = False
        while not success:
            try:
                download(item, glob_pattern=glob_pattern, destdir=destdir,\
                         retries = 10)
                success = True
            except Exception as e:
                success = False
                time.sleep(60)

