import os
import logging
import re
import tarfile
import zipfile
from io import BytesIO
import time
import datetime

from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand

from internetarchive import download
from indigo_api.models import Document, Language, Task, Work, Country, Locality, Commencement, ArbitraryExpressionDate
from egazette.us.states.casemaker_to_akn import Akn30, RefResolver

class Command(BaseCommand):
    help = 'Imports new casemaker files.' \
           'Example: python manage.py add_casemaker --item <internetarchive-item> --destdir <data-dir-for-processing> --globpattern <glob-pattern-for-item-selection>'

    def add_arguments(self, parser):
        parser.add_argument('-i', '--item', dest= 'item', action='store', \
                            help = 'item on internet-archive')
        parser.add_argument('-d', '--destdir', dest= 'destdir', action='store',\
                            help = 'dest dir for processing')
        parser.add_argument('-m', '--mediaurl', dest= 'mediaurl', \
                            action='store', help = 'URL prefix holding images')
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

    def import_akn_doc(self, user, work, date, language, akndoc):
        docxml = akndoc.getvalue().decode('utf-8')
        document = Document()
        document.document_xml = docxml
        document.work = work
        document.expression_date = date
        document.language = language
        document.created_by_user = user
        document.draft = False
        document.updated_by_user = user
        document.save_with_revision(user)
        #self.create_review_task(document, user)

    def add_akn(self, user, frbr_uri, country_name, locality_name, publishdate,\
                actyear, actnum, doctype, title, akndoc):
        country_name = country_name.upper()
        locality_name = locality_name.lower()
        country  = Country.objects.get(country_id =  country_name)
        locality = Locality.objects.get(code = locality_name, \
                                        country = country)

        language = Language.objects.get(language_id='en')            

        work = self.get_work(frbr_uri)
        if work == None:
            start_date = datetime.date(int(actyear), 1, 1)
            work = self.create_work(user, frbr_uri, title, \
                                    start_date, country, locality)
        if work == None:
            self.logger.warning('Could not add the work: %s', frbr_uri)
            return
        if  work.document_set.undeleted().filter(expression_date=publishdate, \
                                                 language=language):    
            self.logger.warning('Document for %s %s exists for language %s', \
                               actyear, actnum, language)
        else:
             self.import_akn_doc(user, work, publishdate, language, akndoc) 
        self.insert_consolidation_date(user, work, publishdate)

    def insert_consolidation_date(self, user, work, publishdate):
        try:
            expr_date = ArbitraryExpressionDate.objects.get(date = publishdate, work = work)
            if expr_date != None:
                return
        except ArbitraryExpressionDate.DoesNotExist:
            pass 

        expr_date = ArbitraryExpressionDate()
        expr_date.date = publishdate
        expr_date.work = work
        expr_date.created_by_user = user
        expr_date.updated_by_user = user
        expr_date.save()

    
    def get_work(self, frbr_uri):
        try:
            work = Work.objects.get(frbr_uri=frbr_uri)
        except Work.DoesNotExist:
            work = None
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
   
    def create_work(self, user, frbr_uri, title, start_date, country,locality):

        work = Work()

        work.frbr_uri  = frbr_uri
        work.country   = country
        work.locality  = locality 
        work.title     = title
        work.commenced = True

        work.created_by_user  = user
        work.updated_by_user  = user
        work.publication_date = start_date 

        try:
            work.full_clean()
            work.save_with_revision(user)
        except ValidationError as e:
            logger = logging.getLogger('import.bareacts')
            logger.warning('Error in adding work for %s: %s', frbr_uri, e)
            return None

        self.create_commencement(work, user, start_date)
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
        mediaurl     = options['mediaurl']
        glob_pattern = options['globpattern']

        self.download_item(item, glob_pattern, destdir)

        #dirname = glob_pattern.split('/')[0]
        user = self.get_user()
        dirpath = os.path.join(destdir, item, glob_pattern)
        self.process_state(user, dirpath, mediaurl)

    def process_recursive(self, user, dirpath, mediaurl):    
        for filename in os.listdir(dirpath):
            filepath = os.path.join(dirpath, filename)
            if os.path.isdir(filepath):
                self.process_recursive(user, filepath, mediaurl)
            elif re.search('\.(tar|zip)$', filepath):
                self.process_state(user, filepath, mediaurl)

    def find_xml_dir(self, dirpath):
        for filename in os.listdir(dirpath):
            filepath = os.path.join(dirpath, filename)
            if os.path.isdir(filepath):
                if filename == 'XML':
                    return filepath
                else:
                    fpath = self.find_xml_dir(filepath)
                    if fpath != None:
                        return fpath
        return None           

    def process_state(self, user, filepath, mediaurl):
         outpath = re.sub('\.(tar|zip)$', '', filepath)

         if not os.path.exists(outpath):
             if filepath.endswith('tar'):
                 f = tarfile.open (filepath)
             else:
                 f = zipfile.ZipFile(filepath, 'r') 

             f.extractall(outpath)

         xmldir = self.find_xml_dir(outpath)
         if not xmldir:
             self.logger.warn('No XML directory found in %s', outpath)
             return

         akn30 = Akn30(mediaurl)
         regulations = {}

         for filename in os.listdir(xmldir):
             xmlpath = os.path.join(xmldir, filename)
             if not os.path.isdir(xmlpath):
                 akn30.process_casemaker(xmlpath, regulations)

         refresolver = RefResolver()
         for num, regulation in regulations.items():
             if num == None:
                 continue

             refresolver.add_regulation(regulation)    

         for num, regulation in regulations.items():
             if num == None:
                 continue

             refresolver.resolve(regulation) 
         for num, regulation in regulations.items():

             if num == None:
                 self.logger.warn('No num found %s', regulation)
                 continue
 
             frbr_uri    = regulation.get_frbr_uri()
             title       = regulation.get_title()
             publishdate = regulation.get_publish_date()
             country     = regulation.get_country()
             locality    = regulation.get_locality()
             regyear     = regulation.get_regyear()
             regnum      = regulation.get_regnum()

             #if regnum not in ['5']:
             #    continue

             akndoc   = BytesIO()
             regulation.write_akn_xml(akndoc, xml_decl = False)

             self.add_akn(user, frbr_uri, country, locality, publishdate, \
                          regyear, regnum, 'regulation', title, akndoc)

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

