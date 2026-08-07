import os
import tempfile

from django.test import SimpleTestCase

from gazettes.services.storage import (
    AssetStorage,
    InvalidRelurl,
    validate_relurl,
)


class ValidateRelurlTests(SimpleTestCase):
    def test_accepts_a_normal_relurl(self):
        self.assertEqual(
            validate_relurl('central_extraordinary/2024-04-18/253767'),
            'central_extraordinary/2024-04-18/253767',
        )

    def test_strips_surrounding_slashes(self):
        self.assertEqual(validate_relurl('/andhra/2018-05-04/2758/'),
                         'andhra/2018-05-04/2758')

    def test_rejects_traversal(self):
        # The relurl decides where an uploaded file is written, so anything
        # that could climb out of the data root has to be refused.
        for bad in ('../../etc/passwd',
                    'andhra/../../etc/passwd',
                    'andhra/./2018/1',
                    '..',
                    'andhra/..'):
            with self.subTest(relurl=bad):
                with self.assertRaises(InvalidRelurl):
                    validate_relurl(bad)

    def test_rejects_single_component(self):
        # Every gazette lives under a source directory.
        with self.assertRaises(InvalidRelurl):
            validate_relurl('andhra')

    def test_rejects_empty_and_non_string(self):
        for bad in ('', None, 123, '   '):
            with self.subTest(relurl=bad):
                with self.assertRaises(InvalidRelurl):
                    validate_relurl(bad)

    def test_rejects_shell_and_null_characters(self):
        for bad in ('andhra/2018/a b', 'andhra/2018/a;b', 'andhra/2018/a\x00b',
                    'andhra/2018/a|b', 'andhra/$(x)/1'):
            with self.subTest(relurl=bad):
                with self.assertRaises(InvalidRelurl):
                    validate_relurl(bad)

    def test_rejects_overlong(self):
        with self.assertRaises(InvalidRelurl):
            validate_relurl('andhra/' + 'a' * 600)


class AssetStorageTests(SimpleTestCase):
    def setUp(self):
        self.first = tempfile.mkdtemp()
        self.second = tempfile.mkdtemp()
        self.storage = AssetStorage(roots=[self.first, self.second],
                                    write_root=self.first)

    def _write(self, root, kind, relative, content='x'):
        path = os.path.join(root, kind, relative)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, 'w') as handle:
            handle.write(content)
        return path

    def test_find_searches_roots_in_order(self):
        # The point of multiple roots is a small writable one in front of a
        # large read-only archive.
        self._write(self.second, 'html', 'andhra/2018/1.html', 'archive copy')
        self.assertEqual(self.storage.read_text('html', 'andhra/2018/1'),
                         'archive copy')

        self._write(self.first, 'html', 'andhra/2018/1.html', 'newer copy')
        self.assertEqual(self.storage.read_text('html', 'andhra/2018/1'),
                         'newer copy')

    def test_find_returns_none_when_absent(self):
        self.assertIsNone(self.storage.find('html', 'andhra/2018/9'))
        self.assertIsNone(self.storage.read('html', 'andhra/2018/9'))
        self.assertIsNone(self.storage.size('raw', 'andhra/2018/9'))

    def test_raw_extension_is_discovered(self):
        # Raw files keep whatever extension the download had.
        self._write(self.first, 'raw', 'andhra/2018/1.pdf', 'pdf bytes')
        self.assertTrue(
            self.storage.find('raw', 'andhra/2018/1').endswith('.pdf')
        )

    def test_save_writes_under_the_write_root(self):
        path = self.storage.save('html', 'andhra/2018/2', b'<p>hello</p>')
        self.assertTrue(path.startswith(self.first))
        self.assertEqual(self.storage.read('html', 'andhra/2018/2'),
                         b'<p>hello</p>')

    def test_save_leaves_no_temporary_file_behind(self):
        self.storage.save('html', 'andhra/2018/3', b'body')
        directory = os.path.join(self.first, 'html', 'andhra/2018')
        self.assertEqual(sorted(os.listdir(directory)), ['3.html'])

    def test_save_rejects_traversal(self):
        with self.assertRaises(InvalidRelurl):
            self.storage.save('html', '../../escape/1', b'nope')

    def test_save_overwrites_atomically(self):
        self.storage.save('html', 'andhra/2018/4', b'first')
        self.storage.save('html', 'andhra/2018/4', b'second')
        self.assertEqual(self.storage.read('html', 'andhra/2018/4'), b'second')
