import argparse
import os
import codecs
import re

from google.cloud import translate

def translate_text(text, project_id, from_lang, to_lang):
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

    return ''.join([t.translated_text for t in response.translations])

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Using Google API to translate text')
    parser.add_argument('-t', '--type', dest='input_type', action='store',\
                       default='text', help='type of input file(text/')
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
    args = parser.parse_args()

    os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = args.key_file
    project_id = args.project_id
    from_lang  = args.input_lang
    to_lang    = args.output_lang

    inhandle = codecs.open(args.input_file, 'r', 'utf8')
    outhandle = codecs.open(args.output_file, 'w', 'utf-8')
    text = inhandle.read()
    inhandle.close()

    if args.input_type == 'text':
        translated_text =  translate_text(text, args.project_id, \
                                          args.input_lang, args.output_lang)
        if translated_text:  
            outhandle.write(translated_text)


    elif args.input_type == 'sbv':
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
      
    outhandle.close()
