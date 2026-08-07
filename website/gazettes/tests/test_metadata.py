import datetime

from django.test import SimpleTestCase

from gazettes.services import metadata
from gazettes.services.sources import get_identifier
from gazettes.tests.factories import CENTRAL_XML, WBSL_XML


class ParseTests(SimpleTestCase):
    def test_parses_a_dated_gazette(self):
        info = metadata.parse_metainfo(CENTRAL_XML, 'central_extraordinary/x/1')
        self.assertEqual(info['date'], datetime.date(2024, 4, 18))
        self.assertEqual(info['ministry'], 'Ministry of Railways')

    def test_rejects_malformed_xml(self):
        with self.assertRaises(metadata.MetadataError):
            metadata.parse_metainfo(b'<document><unclosed>', 'andhra/x/1')

    def test_accepts_bytes_and_str(self):
        self.assertIsNotNone(
            metadata.parse_metainfo(CENTRAL_XML.encode('utf-8'), 'a/b/c')
        )


class ExtractFieldsTests(SimpleTestCase):
    def test_promotes_the_queryable_tags(self):
        info = metadata.parse_metainfo(CENTRAL_XML, 'central_extraordinary/x/1')
        fields = metadata.extract_fields(info, 'Extraordinary Gazette of India')

        self.assertEqual(fields['date'], datetime.date(2024, 4, 18))
        self.assertEqual(fields['year'], 2024)
        self.assertEqual(fields['ministry'], 'Ministry of Railways')
        self.assertEqual(fields['department'], 'Construction Department')
        self.assertEqual(fields['office'], 'East Central Railway')
        self.assertTrue(fields['source_url'].endswith('253767.pdf'))

    def test_keeps_unpromoted_tags_in_metadata(self):
        # gazetteid has no column of its own but must not be lost.
        info = metadata.parse_metainfo(CENTRAL_XML, 'central_extraordinary/x/1')
        fields = metadata.extract_fields(info, 'series')
        self.assertEqual(fields['metadata']['gazetteid'],
                         'CG-BR-E-18042024-253767')

    def test_metadata_is_json_serialisable(self):
        import json

        info = metadata.parse_metainfo(CENTRAL_XML, 'central_extraordinary/x/1')
        fields = metadata.extract_fields(info, 'series')
        # The date became an ISO string rather than a date object.
        json.dumps(fields['metadata'])
        self.assertEqual(fields['metadata']['date'], '2024-04-18')

    def test_undated_source_still_gets_a_year(self):
        # West Bengal archive scans are catalogued by year with no date.
        info = metadata.parse_metainfo(WBSL_XML, 'wbsl/x/1')
        fields = metadata.extract_fields(info, 'WBSL Archive')

        self.assertIsNone(fields['date'])
        self.assertEqual(fields['year'], 1885)

    def test_title_falls_back_to_subject_then_to_a_constructed_one(self):
        no_title = """<?xml version="1.0" encoding="utf-8"?>
<document><date><day>1</day><month>2</month><year>2020</year></date>
<subject>Land acquisition</subject></document>"""
        fields = metadata.extract_fields(
            metadata.parse_metainfo(no_title, 'andhra/x/1'), 'Andhra Gazette'
        )
        self.assertEqual(fields['title'], 'Land acquisition')

        bare = """<?xml version="1.0" encoding="utf-8"?>
<document><date><day>1</day><month>2</month><year>2020</year></date>
<gznum>42</gznum></document>"""
        fields = metadata.extract_fields(
            metadata.parse_metainfo(bare, 'andhra/x/1'), 'Andhra Gazette'
        )
        # No gazette in the archive should be listed as untitled.
        self.assertIn('Andhra Gazette', fields['title'])
        self.assertIn('42', fields['title'])
        self.assertIn('2020', fields['title'])

    def test_absurd_year_is_ignored(self):
        bad = """<?xml version="1.0" encoding="utf-8"?>
<document><year>99999</year></document>"""
        fields = metadata.extract_fields(
            metadata.parse_metainfo(bad, 'wbsl/x/1'), 'series'
        )
        self.assertIsNone(fields['year'])

    def test_overlong_char_value_does_not_break_its_column(self):
        long_dept = """<?xml version="1.0" encoding="utf-8"?>
<document><department>%s</department></document>""" % ('x' * 900)
        fields = metadata.extract_fields(
            metadata.parse_metainfo(long_dept, 'andhra/x/1'), 'series'
        )
        self.assertEqual(fields['department'], '')
        # It survives where length is not constrained.
        self.assertEqual(len(fields['metadata']['department']), 900)


class IdentifierTests(SimpleTestCase):
    def test_matches_the_scrapers_identifier(self):
        # /details/<identifier>/ must resolve the same item as the Internet
        # Archive, so this has to stay delegated to datasrcs_info.
        info = metadata.parse_metainfo(CENTRAL_XML, 'central_extraordinary/x/1')
        identifier = get_identifier(
            'central_extraordinary/2024-04-18/253767', info
        )
        self.assertEqual(identifier,
                         'in.gazette.central.e.2024-04-18.253767')

    def test_source_specific_identifier_function_is_used(self):
        # wbsl identifiers come from the bookid, not the path.
        info = metadata.parse_metainfo(WBSL_XML, 'wbsl/x/1')
        self.assertEqual(get_identifier('wbsl/anything/1', info),
                         'wbsl.WB00123')

    def test_returns_none_when_it_cannot_build_one(self):
        # bihar's identifier function needs a date this metadata lacks.
        info = metadata.parse_metainfo(
            '<?xml version="1.0" encoding="utf-8"?>'
            '<document><subject>No date here</subject></document>',
            'bihar/x/1',
        )
        self.assertIsNone(get_identifier('bihar/x/1', info))

    def test_degenerate_document_is_reported_not_crashed(self):
        # '<document/>' makes the scraper's reader return a bare string; that
        # must surface as bad metadata, not an AttributeError.
        with self.assertRaises(metadata.MetadataError):
            metadata.parse_metainfo(
                '<?xml version="1.0" encoding="utf-8"?><document/>',
                'bihar/x/1',
            )
