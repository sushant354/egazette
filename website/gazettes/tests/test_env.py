"""Tests for the .env reader in egazette_site.settings.

The loader runs before Django is configured, so it is exercised directly here
rather than through the settings module.
"""

import os
import tempfile
from pathlib import Path

from django.core.exceptions import ImproperlyConfigured
from django.test import SimpleTestCase

from egazette_site.settings import load_env_file


class LoadEnvFileTests(SimpleTestCase):
    def write(self, content):
        handle = tempfile.NamedTemporaryFile(
            'w', suffix='.env', delete=False, encoding='utf-8'
        )
        handle.write(content)
        handle.close()
        self.addCleanup(os.unlink, handle.name)
        return handle.name

    def load(self, content, **kwargs):
        """Load into a restored-afterwards copy of os.environ."""
        original = os.environ.copy()
        self.addCleanup(lambda: (os.environ.clear(),
                                 os.environ.update(original)))
        return load_env_file(self.write(content), **kwargs)

    def test_reads_simple_assignments(self):
        self.load('EGAZETTE_TEST_A=one\nEGAZETTE_TEST_B=two\n')
        self.assertEqual(os.environ['EGAZETTE_TEST_A'], 'one')
        self.assertEqual(os.environ['EGAZETTE_TEST_B'], 'two')

    def test_skips_comments_and_blank_lines(self):
        self.load('# a comment\n\n   \nEGAZETTE_TEST_A=one\n')
        self.assertEqual(os.environ['EGAZETTE_TEST_A'], 'one')

    def test_accepts_export_prefix(self):
        # The same file should also be sourceable from a shell.
        self.load('export EGAZETTE_TEST_A=one\n')
        self.assertEqual(os.environ['EGAZETTE_TEST_A'], 'one')

    def test_strips_matching_quotes(self):
        self.load('''EGAZETTE_TEST_A="one two"\nEGAZETTE_TEST_B='three'\n''')
        self.assertEqual(os.environ['EGAZETTE_TEST_A'], 'one two')
        self.assertEqual(os.environ['EGAZETTE_TEST_B'], 'three')

    def test_quoted_value_keeps_a_hash(self):
        # Passwords and generated tokens can contain '#'; it must not be
        # treated as a comment.
        self.load('EGAZETTE_TEST_A="pa#ss word"\n')
        self.assertEqual(os.environ['EGAZETTE_TEST_A'], 'pa#ss word')

    def test_value_may_contain_equals(self):
        # base64/urlsafe secrets end in '='.
        self.load('EGAZETTE_TEST_A=abc=def==\n')
        self.assertEqual(os.environ['EGAZETTE_TEST_A'], 'abc=def==')

    def test_empty_value_is_allowed(self):
        # An empty EGAZETTE_INGEST_TOKENS is how the write API is closed.
        self.load('EGAZETTE_TEST_A=\n')
        self.assertEqual(os.environ['EGAZETTE_TEST_A'], '')

    def test_existing_environment_wins_by_default(self):
        # systemd's EnvironmentFile and one-off shell overrides must beat the
        # checked-out file.
        original = os.environ.copy()
        self.addCleanup(lambda: (os.environ.clear(),
                                 os.environ.update(original)))
        os.environ['EGAZETTE_TEST_A'] = 'from environment'
        load_env_file(self.write('EGAZETTE_TEST_A=from file\n'))
        self.assertEqual(os.environ['EGAZETTE_TEST_A'], 'from environment')

    def test_override_forces_the_file_to_win(self):
        original = os.environ.copy()
        self.addCleanup(lambda: (os.environ.clear(),
                                 os.environ.update(original)))
        os.environ['EGAZETTE_TEST_A'] = 'from environment'
        load_env_file(self.write('EGAZETTE_TEST_A=from file\n'), override=True)
        self.assertEqual(os.environ['EGAZETTE_TEST_A'], 'from file')

    def test_missing_file_is_not_an_error(self):
        self.assertFalse(load_env_file('/nonexistent/path/to/.env'))

    def test_directory_is_not_an_error(self):
        self.assertFalse(load_env_file(tempfile.mkdtemp()))

    def test_malformed_line_is_reported_with_its_number(self):
        # A typo that silently did nothing would surface much later as a
        # baffling configuration bug.
        with self.assertRaises(ImproperlyConfigured) as caught:
            self.load('EGAZETTE_TEST_A=one\nthis line has no equals sign\n')
        self.assertIn(':2', str(caught.exception))

    def test_invalid_variable_name_is_reported(self):
        with self.assertRaises(ImproperlyConfigured):
            self.load('not a name=value\n')


class ShippedEnvExampleTests(SimpleTestCase):
    """deploy/env.example is what a new deployment copies; it must parse."""

    def test_example_file_parses(self):
        example = (
            Path(__file__).resolve().parent.parent.parent
            / 'deploy' / 'env.example'
        )
        self.assertTrue(example.is_file(), 'deploy/env.example is missing')

        original = os.environ.copy()
        self.addCleanup(lambda: (os.environ.clear(),
                                 os.environ.update(original)))
        self.assertTrue(load_env_file(example))
