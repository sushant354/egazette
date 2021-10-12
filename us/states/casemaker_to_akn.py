import lxml.etree as ET
import sys
import logging


class Metadata:
    def __init__(self):
        self.d = {}

    def get_value(self, k):
        if k in self.d:
            return self.d[k]
        return ''

    def set_value(self, k, v):
        self.d[k] = v

class Akn30:
    def __init__(self):
        self.localities = {'MI': 'michigan'}
        self.logger = logging.getLogger('akn30')
    
    def get_header(self, metadata):
        title       = metadata.get_value('title')
        locality    = metadata.get_value('locality')
        regyear     = metadata.get_value('regyear')
        regnum      = metadata.get_value('regnum')
        publishdate = metadata.get_value('publishdate')
        passedby    = metadata.get_value('passedby')

        frbr_uri = '/akn/us-%s/act/regulations/%s/%s' % (locality, regyear, regnum)

        frbr_work = '''
          <FRBRthis value="%s/!main" />
          <FRBRuri value="%s"/>
          <FRBRalias value="%s" name="title"/>
          <FRBRdate date="%s" name="Generation"/>
          <FRBRauthor href="#council"/>
          <FRBRcountry value="us-%s"/>
          <FRBRsubtype value="regulations"/>
          <FRBRnumber value="%s"/>
        ''' % (frbr_uri, frbr_uri, title, regyear, locality, regnum)

        frbr_expr = '''
          <FRBRthis value="%s/!main"/>
          <FRBRuri value="%s/en@%s"/>
          <FRBRdate date="%s" name="Generation"/>
          <FRBRauthor href="%s"/>
          <FRBRlanguage language="en"/>
        ''' % (frbr_uri, frbr_uri, publishdate, publishdate, passedby)

        frbr_manifest = '''
          <FRBRthis value="%s/!main"/>
          <FRBRuri value="%s/en@%s"/>
          <FRBRdate date="%s" name="Generation"/>
          <FRBRauthor href="#iklaws"/>
        ''' % (frbr_uri, frbr_uri, publishdate, publishdate)

        header = '''
    <akomaNtoso xmlns="http://docs.oasis-open.org/legaldocml/ns/akn/3.0">

  <act contains="originalVersion" name="act">
    <meta>
      <identification source="#iklaws">
        <FRBRWork>
        %s
        </FRBRWork>
        <FRBRExpression>
        %s
        </FRBRExpression>
        <FRBRManifestation>
        %s
        </FRBRManifestation>
      </identification>
      <publication number="" name="" showAs="" date="%s"/>
    </meta>''' % (frbr_work, frbr_expr, frbr_manifest, publishdate)

        return header


    def get_metadata(self, xmldom):
        metadata = Metadata()
        number_node = xmldom.xpath("//code[@type='Section']/number/text()")
        print (number_node)
        if number_node:
            metadata.set_value('regnum', number_node.text)
        
        return metadata

    def to_akn(self, xml_file, outhandle):
        xmldom = ET.parse(xml_file)
        metadata = self.get_metadata(xmldom)
        header = self.get_header(metadata)
        outhandle.write(header)


if __name__ == '__main__':
    xml_file = sys.argv[1]
    fhandle = open(sys.argv[2], 'w', encoding = 'utf-8')

    akn30 = Akn30()
    outxml = akn30.to_akn(xml_file, fhandle)

    fhandle.close()
