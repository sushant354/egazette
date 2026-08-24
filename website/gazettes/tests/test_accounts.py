"""Accounts and bookmarks: the reader-written half of the site."""

import shutil
import tempfile

from django.contrib.auth.models import User
from django.test import TestCase, override_settings
from django.urls import reverse

from gazettes.models import Bookmark, Gazette
from gazettes.services import sources as sources_service
from gazettes.services.ingest import IngestService
from gazettes.services.storage import AssetStorage
from gazettes.tests.factories import WBSL_XML, write_gazette

RELURL = 'central_extraordinary/2024-04-18/253767'
IDENTIFIER = 'in.gazette.central.e.2024-04-18.253767'

# An undated source, keyed by bookid rather than date.
SECOND_RELURL = 'wbsl/calcutta/1885'

PASSWORD = 'a-long-enough-passphrase'


class AccountTestCase(TestCase):
    def setUp(self):
        self.datadir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.datadir, ignore_errors=True)

        patcher = override_settings(
            GAZETTE_DATA_ROOTS=[self.datadir],
            GAZETTE_WRITE_ROOT=self.datadir,
        )
        patcher.enable()
        self.addCleanup(patcher.disable)

        self.storage = AssetStorage(roots=[self.datadir],
                                    write_root=self.datadir)
        self.service = IngestService(storage=self.storage)

    def ingest(self, relurl=RELURL, **kwargs):
        write_gazette(self.datadir, relurl, **kwargs)
        result = self.service.ingest(relurl)
        assert result.ok, result.reason
        sources_service.refresh_counts()
        return Gazette.objects.get(relurl=relurl)

    def make_user(self, username='reader'):
        return User.objects.create_user(username=username, password=PASSWORD)

    def sign_in(self, username='reader'):
        user = self.make_user(username)
        self.client.force_login(user)
        return user


class SignupTests(AccountTestCase):
    def test_signup_creates_an_account_and_signs_it_in(self):
        response = self.client.post(reverse('gazettes:signup'), {
            'username': 'newreader',
            'email': 'newreader@example.com',
            'password1': PASSWORD,
            'password2': PASSWORD,
        })

        self.assertEqual(response.status_code, 302)
        self.assertTrue(User.objects.filter(username='newreader').exists())
        self.assertEqual(int(self.client.session['_auth_user_id']),
                         User.objects.get(username='newreader').pk)

    def test_signup_returns_to_the_page_the_reader_came_from(self):
        self.ingest()
        target = reverse('gazettes:detail', args=[IDENTIFIER])

        response = self.client.post(reverse('gazettes:signup'), {
            'username': 'newreader',
            'email': 'newreader@example.com',
            'password1': PASSWORD,
            'password2': PASSWORD,
            'next': target,
        })

        self.assertRedirects(response, target)

    def test_signup_will_not_redirect_off_site(self):
        response = self.client.post(reverse('gazettes:signup'), {
            'username': 'newreader',
            'email': 'newreader@example.com',
            'password1': PASSWORD,
            'password2': PASSWORD,
            'next': 'https://evil.example.com/',
        })

        self.assertRedirects(response, reverse('gazettes:home'))

    def test_an_account_needs_an_email_address(self):
        response = self.client.post(reverse('gazettes:signup'), {
            'username': 'newreader',
            'password1': PASSWORD,
            'password2': PASSWORD,
        })

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'This field is required')
        self.assertFalse(User.objects.filter(username='newreader').exists())

    def test_a_malformed_email_is_refused(self):
        response = self.client.post(reverse('gazettes:signup'), {
            'username': 'newreader',
            'email': 'not-an-address',
            'password1': PASSWORD,
            'password2': PASSWORD,
        })

        self.assertEqual(response.status_code, 200)
        self.assertFalse(User.objects.filter(username='newreader').exists())

    def test_an_address_is_taken_only_once(self):
        User.objects.create_user(username='first', password=PASSWORD,
                                 email='taken@example.com')

        response = self.client.post(reverse('gazettes:signup'), {
            'username': 'second',
            'email': 'TAKEN@example.com',
            'password1': PASSWORD,
            'password2': PASSWORD,
        })

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'already exists')
        self.assertFalse(User.objects.filter(username='second').exists())

    def test_a_weak_password_is_refused(self):
        response = self.client.post(reverse('gazettes:signup'), {
            'username': 'newreader',
            'email': 'newreader@example.com',
            'password1': 'password',
            'password2': 'password',
        })

        self.assertEqual(response.status_code, 200)
        self.assertFalse(User.objects.filter(username='newreader').exists())


class SignInTests(AccountTestCase):
    def test_login_page_keeps_the_archives_own_name(self):
        # LoginView fills site_name from the Sites framework, which would
        # otherwise put the bare hostname in the masthead on this one page.
        response = self.client.get(reverse('gazettes:login'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Indian Gazettes')
        self.assertNotContains(response, 'testserver')

    def test_sign_in_and_out(self):
        self.make_user()

        response = self.client.post(reverse('gazettes:login'),
                                    {'username': 'reader',
                                     'password': PASSWORD})
        self.assertRedirects(response, reverse('gazettes:home'))
        self.assertIn('_auth_user_id', self.client.session)

        response = self.client.post(reverse('gazettes:logout'))
        self.assertRedirects(response, reverse('gazettes:home'))
        self.assertNotIn('_auth_user_id', self.client.session)

    def test_signing_out_needs_a_post(self):
        self.sign_in()
        response = self.client.get(reverse('gazettes:logout'))
        self.assertEqual(response.status_code, 405)
        self.assertIn('_auth_user_id', self.client.session)

    def test_signing_in_lands_on_the_page_that_asked_for_it(self):
        self.make_user()
        target = reverse('gazettes:bookmarks')

        response = self.client.post(
            '%s?next=%s' % (reverse('gazettes:login'), target),
            {'username': 'reader', 'password': PASSWORD},
        )
        self.assertRedirects(response, target)

    def test_a_next_pointing_back_at_login_does_not_loop(self):
        self.sign_in()
        response = self.client.get(
            reverse('gazettes:login'),
            {'next': reverse('gazettes:login')},
        )
        self.assertRedirects(response, reverse('gazettes:home'))


class HeaderTests(AccountTestCase):
    def test_signed_out_header_offers_sign_in(self):
        response = self.client.get(reverse('gazettes:home'))
        self.assertContains(response, 'Sign in')
        self.assertContains(response, 'Create account')

    def test_sign_in_link_carries_the_current_page(self):
        self.ingest()
        target = reverse('gazettes:detail', args=[IDENTIFIER])
        response = self.client.get(target)
        self.assertContains(response, 'next=%s' % target.replace('/', '%2F'))

    def test_signed_in_header_shows_the_account_menu_and_bookmarks(self):
        gazette = self.ingest()
        user = self.sign_in()
        Bookmark.objects.create(user=user, gazette=gazette)

        response = self.client.get(reverse('gazettes:home'))
        self.assertContains(response, 'account-dropdown')
        self.assertContains(response, 'reader')
        # The saved gazette is listed in the menu itself.
        self.assertContains(response, gazette.title[:40])
        self.assertContains(response, 'Sign out')

    def test_the_menu_says_so_when_nothing_is_saved(self):
        self.sign_in()
        response = self.client.get(reverse('gazettes:home'))
        self.assertContains(response, 'Nothing saved yet')

    def test_a_long_list_is_cut_short_with_a_link_to_the_rest(self):
        user = self.sign_in()
        for index in range(9):
            gazette = self.ingest('central_extraordinary/2024-04-18/%d' % index)
            Bookmark.objects.create(user=user, gazette=gazette)

        response = self.client.get(reverse('gazettes:home'))
        body = response.content.decode()

        # Six in the menu, and the count of everything saved beside them.
        self.assertEqual(body.count('account-bookmark-title'), 6)
        self.assertIn('All 9 bookmarks', body)

    def test_an_error_page_still_renders_the_menu(self):
        # The account context processor runs on every rendered page, 404s
        # included, where there is no view to supply anything.
        self.sign_in()
        response = self.client.get('/details/in.gazette.nope.1/')
        self.assertEqual(response.status_code, 404)
        self.assertContains(response, 'account-dropdown', status_code=404)


class BookmarkTests(AccountTestCase):
    def test_bookmarking_needs_an_account(self):
        self.ingest()
        response = self.client.post(
            reverse('gazettes:bookmark', args=[IDENTIFIER]), {'action': 'add'}
        )

        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse('gazettes:login'), response['Location'])
        self.assertEqual(Bookmark.objects.count(), 0)

    def test_add_and_remove(self):
        gazette = self.ingest()
        user = self.sign_in()
        url = reverse('gazettes:bookmark', args=[IDENTIFIER])

        response = self.client.post(url, {'action': 'add'})
        self.assertRedirects(response, gazette.get_absolute_url())
        self.assertTrue(
            Bookmark.objects.filter(user=user, gazette=gazette).exists()
        )

        self.client.post(url, {'action': 'remove'})
        self.assertFalse(
            Bookmark.objects.filter(user=user, gazette=gazette).exists()
        )

    def test_repeating_add_does_not_duplicate_or_flip_back(self):
        gazette = self.ingest()
        user = self.sign_in()
        url = reverse('gazettes:bookmark', args=[IDENTIFIER])

        self.client.post(url, {'action': 'add'})
        self.client.post(url, {'action': 'add'})

        self.assertEqual(
            Bookmark.objects.filter(user=user, gazette=gazette).count(), 1
        )

    def test_without_an_action_it_toggles(self):
        gazette = self.ingest()
        self.sign_in()
        url = reverse('gazettes:bookmark', args=[IDENTIFIER])

        self.client.post(url)
        self.assertEqual(Bookmark.objects.count(), 1)
        self.client.post(url)
        self.assertEqual(Bookmark.objects.count(), 0)

    def test_it_returns_the_reader_to_the_listing_they_were_on(self):
        self.ingest()
        self.sign_in()
        target = '%s?q=land' % reverse('gazettes:search')

        response = self.client.post(
            reverse('gazettes:bookmark', args=[IDENTIFIER]),
            {'action': 'add', 'next': target},
        )
        self.assertRedirects(response, target)

    def test_it_will_not_redirect_off_site(self):
        gazette = self.ingest()
        self.sign_in()

        response = self.client.post(
            reverse('gazettes:bookmark', args=[IDENTIFIER]),
            {'action': 'add', 'next': 'https://evil.example.com/'},
        )
        self.assertRedirects(response, gazette.get_absolute_url())

    def test_a_get_is_refused(self):
        self.ingest()
        self.sign_in()
        response = self.client.get(
            reverse('gazettes:bookmark', args=[IDENTIFIER])
        )
        self.assertEqual(response.status_code, 405)

    def test_unknown_gazette_is_404(self):
        self.sign_in()
        response = self.client.post(
            reverse('gazettes:bookmark', args=['in.gazette.nope.1']),
            {'action': 'add'},
        )
        self.assertEqual(response.status_code, 404)

    def test_one_reader_cannot_see_anothers_bookmarks(self):
        gazette = self.ingest()
        other = self.make_user('someone-else')
        Bookmark.objects.create(user=other, gazette=gazette)

        self.sign_in('reader')
        response = self.client.get(reverse('gazettes:bookmarks'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'not bookmarked any gazettes')

    def test_deleting_a_gazette_takes_its_bookmarks_with_it(self):
        gazette = self.ingest()
        user = self.sign_in()
        Bookmark.objects.create(user=user, gazette=gazette)

        gazette.delete()
        self.assertEqual(Bookmark.objects.count(), 0)


class BookmarkPageTests(AccountTestCase):
    def test_the_page_needs_an_account(self):
        response = self.client.get(reverse('gazettes:bookmarks'))
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse('gazettes:login'), response['Location'])

    def test_it_lists_what_was_saved_newest_first(self):
        first = self.ingest()
        second = self.ingest(SECOND_RELURL, metatags=WBSL_XML)
        user = self.sign_in()

        Bookmark.objects.create(user=user, gazette=first)
        Bookmark.objects.create(user=user, gazette=second)

        response = self.client.get(reverse('gazettes:bookmarks'))
        body = response.content.decode()

        self.assertEqual(response.status_code, 200)
        self.assertIn(first.identifier, body)
        self.assertIn(second.identifier, body)
        self.assertLess(body.index(second.identifier),
                        body.index(first.identifier))

    def test_the_account_page_counts_them(self):
        gazette = self.ingest()
        user = self.sign_in()
        Bookmark.objects.create(user=user, gazette=gazette)

        response = self.client.get(reverse('gazettes:account'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'reader')
        self.assertContains(response, 'Bookmarks')


class BookmarkButtonTests(AccountTestCase):
    def test_the_detail_page_shows_the_saved_state(self):
        gazette = self.ingest()
        user = self.sign_in()

        url = reverse('gazettes:detail', args=[IDENTIFIER])
        self.assertContains(self.client.get(url), 'value="add"')

        Bookmark.objects.create(user=user, gazette=gazette)
        response = self.client.get(url)
        self.assertContains(response, 'value="remove"')
        self.assertContains(response, 'Bookmarked')

    def test_listings_read_every_row_in_one_query(self):
        first = self.ingest()
        second = self.ingest(SECOND_RELURL, metatags=WBSL_XML)
        user = self.sign_in()
        Bookmark.objects.create(user=user, gazette=first)
        Bookmark.objects.create(user=user, gazette=second)

        response = self.client.get(reverse('gazettes:search'))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content.decode().count('value="remove"'), 2)

    def test_signed_out_readers_are_pointed_at_sign_in(self):
        self.ingest()
        response = self.client.get(reverse('gazettes:detail', args=[IDENTIFIER]))

        self.assertContains(response, 'Sign in to bookmark this gazette')
        self.assertNotContains(response, 'gazettes:bookmark')
