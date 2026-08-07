from django.test import SimpleTestCase

from gazettes.templatetags.gazette_extras import intcomma_in, without


class IntcommaInTests(SimpleTestCase):
    def test_groups_digits_the_indian_way(self):
        # Counts here run into the lakhs; Django's humanize groups in
        # thousands, which reads wrong for this audience.
        self.assertEqual(intcomma_in(0), '0')
        self.assertEqual(intcomma_in(999), '999')
        self.assertEqual(intcomma_in(1000), '1,000')
        self.assertEqual(intcomma_in(99999), '99,999')
        self.assertEqual(intcomma_in(100000), '1,00,000')
        self.assertEqual(intcomma_in(466219), '4,66,219')
        self.assertEqual(intcomma_in(12345678), '1,23,45,678')

    def test_handles_negatives(self):
        self.assertEqual(intcomma_in(-100000), '-1,00,000')

    def test_passes_through_what_it_cannot_parse(self):
        self.assertEqual(intcomma_in(None), '')
        self.assertEqual(intcomma_in('not a number'), 'not a number')


class WithoutTests(SimpleTestCase):
    def test_removes_one_entry_and_keeps_the_rest(self):
        self.assertEqual(without(['a', 'b', 'c'], 'b'), ['a', 'c'])

    def test_absent_entry_is_a_no_op(self):
        self.assertEqual(without(['a'], 'z'), ['a'])

    def test_handles_empty(self):
        self.assertEqual(without([], 'a'), [])
        self.assertEqual(without(None, 'a'), [])
