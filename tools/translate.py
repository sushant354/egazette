import argparse
import os
import codecs
import re
import cgi

from bs4 import BeautifulSoup, NavigableString, Tag
from bs4 import Comment, Declaration, CData, ProcessingInstruction, Doctype

from google.cloud import translate

def translate_text(text, project_id, from_lang, to_lang):
    if re.match('[\s,()=-]*$', text):
        return text

    """Translating Text."""

    client = translate.TranslationServiceClient()

    location = "global"

    parent = f"projects/{project_id}/locations/{location}"

    # Detail on supported types can be found here:
    # https://cloud.google.com/translate/docs/supported-formats
    response = client.translate_text(
        request={
            "parent": parent,
            "contents": [text],
            "mime_type": "text/plain",  # mime types: text/plain, text/html
            "source_language_code": from_lang,
            "target_language_code": to_lang,
        }
    )

    final = ''.join([t.translated_text for t in response.translations])

    return final

def get_arg_parser():
    parser = argparse.ArgumentParser(description='Using Google API to translate text')
    parser.add_argument('-t', '--type', dest='input_type', action='store',\
                       default='text', help='type of input file(text/sbv/html)')
    parser.add_argument('-l', '--input_lang', dest='input_lang', \
                        required= True,  \
                        action='store', help='Language of input text (https://cloud.google.com/translate/docs/languages)')
    parser.add_argument('-L', dest='output_lang', \
                        required= True,  \
                        action='store', help='Language of output text')

    parser.add_argument('-i', '--infile', dest='input_file', required= True, \
                         action='store', help='Input File')
    parser.add_argument('-o', '--outfile', dest='output_file', required= True,\
                         action='store', help='Output file')

    parser.add_argument('-k', '--key', dest='key_file', required= True,  \
                         action='store', help='Google key file')
    parser.add_argument('-p', '--project', dest='project_id', required= True, \
                         action='store', help='Project ID')
    parser.add_argument('-c', '--ignoreclass', dest='ignore_classes', \
                         required=False, action='append', \
                         help='HTML classes to be ignored for translation')
    return parser                     

def process_sbv(text, outhandle, project_id, from_lang, to_lang):
    start = True
    lines = []
    for line in text.splitlines():
        if start and re.match('\d{1,2}:\d\d:\d\d.\d+,\d{1,2}:\d\d:\d\d.\d+$', line):
            outhandle.write(line)
            outhandle.write('\n')
            start = False
            lines = []
        elif not start and line == '':
            para = '\n'.join(lines)
            new_para = translate_text(para, project_id, from_lang, to_lang)
            outhandle.write(new_para)
            outhandle.write('\n\n')
            start = True
            lines = []
        else:
            lines.append(line)

    if lines:
        para = '\n'.join(lines)
        new_para = translate_text(para, project_id, from_lang, to_lang)
        outhandle.write(new_para)

class HtmlProcessor:
    def __init__(self, project_id, from_lang, to_lang, ignore_classes):
        self.project_id = project_id
        self.from_lang  = from_lang
        self.to_lang    = to_lang
        self.ignoretypes =  [Comment, Declaration, CData, ProcessingInstruction]
        self.linebreaks  = ['br', 'p', 'div', 'dir']
        self.ignoretags  = ['script', 'style']
        self.ignore_classes = set(ignore_classes)

    def process_html(self, text, outhandle):
        d = BeautifulSoup(text, 'html5lib')
        self.process_children(d, outhandle)

    def translate(self, text):
        translated_text = translate_text(text, self.project_id, \
                                    self.from_lang, self.to_lang)
        return translated_text

    def is_attr_translate(self, tag, attr):
        if (tag == 'img' and attr == 'alt') or \
                (tag == 'meta' and attr == 'content'):
            return True

        return False

    def process_children(self, d, outhandle):
        for content in d.contents:
            if type(content) == NavigableString:
                text = '%s' % content
                translated_text = self.translate(text)
                if translated_text:
                    outhandle.write(cgi.escape(translated_text))
            elif type(content) in self.ignoretypes:
                 outhandle.write('%s' % content)
            elif isinstance(content, Doctype):
                 outhandle.write('<!DOCTYPE %s>\n' % content)
            elif type(content) == Tag:
                 classes = content.get('class')
                 ignore  = False
                 if classes:
                     for c in classes:
                         if c in self.ignore_classes:
                             ignore = True

                 if ignore or (content.name in self.ignoretags):
                     outhandle.write('%s' % content)
                     continue

                 attrs = []
                 for k, v in content.attrs.items():
                     if isinstance(v, list):
                          v = ' '.join(v)

                     if self.is_attr_translate(content.name, k):
                         v = self.translate(v)

                     v = cgi.escape(v)
                     attrs.append('%s="%s"' % (k, v))

                 if attrs:
                     outhandle.write('<%s %s>' % (content.name, ' '.join(attrs)))
                 else:    
                     outhandle.write('<%s>' % content.name)

                 if content.name in self.linebreaks:
                     outhandle.write('\n')

                 self.process_children(content, outhandle)

                 outhandle.write('</%s>' % content.name)
                 if content.name in self.linebreaks:
                     outhandle.write('\n')
     

if __name__ == '__main__':
    parser = get_arg_parser()
    args   = parser.parse_args()

    project_id = args.project_id
    from_lang  = args.input_lang
    to_lang    = args.output_lang
    ignore_classes = args.ignore_classes

    os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = args.key_file

    inhandle = codecs.open(args.input_file, 'r', 'utf8')
    outhandle = codecs.open(args.output_file, 'w', 'utf-8')
    text = inhandle.read()
    inhandle.close()

    if args.input_type == 'text':
        translated_text =  translate_text(text, project_id, from_lang, to_lang)
        if translated_text:  
            outhandle.write(translated_text)


    elif args.input_type == 'sbv':
        process_sbv(text, outhandle, project_id, from_lang, to_lang)
    elif args.input_type == 'html':
        htmlprocessor = HtmlProcessor(project_id, from_lang, to_lang, \
                                      ignore_classes)
        htmlprocessor.process_html(text, outhandle)
      
    outhandle.close()
