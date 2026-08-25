from unittest import mock

from django.urls import reverse

from bilbyui.tests.test_app_container import empty_gwflow_jobs_side_effect
from bilbyui.tests.testcases import BilbyTestCase


class BaseShellTemplateTest(BilbyTestCase):
    """Render assertions for the shared shell markup (base.html + _navbar.html)."""

    url = "/gwflow/"

    def setUp(self):
        self.authenticate()

    def _get_content(self):
        with mock.patch(
            "bilbyui.views.list_gwflow_jobs",
            side_effect=empty_gwflow_jobs_side_effect(),
        ):
            response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        return response.content.decode()

    def _anchor_containing(self, content, marker):
        marker_pos = content.index(marker)
        start = content.rindex("<a", 0, marker_pos)
        end = content.index("</a>", marker_pos) + len("</a>")
        return content[start:end]

    def test_viewport_meta_rendered_immediately_after_charset(self):
        content = self._get_content()
        self.assertIn('<meta name="viewport" content="width=device-width, initial-scale=1">', content)

        charset_end = content.index('<meta charset="utf-8">') + len('<meta charset="utf-8">')
        viewport_pos = content.index('<meta name="viewport"')
        self.assertEqual(content[charset_end:viewport_pos].strip(), "")

    def test_skip_link_is_first_element_in_body(self):
        content = self._get_content()
        body_pos = content.index("<body>")
        skip_pos = content.index('class="skip-link"')
        navbar_pos = content.index("<nav")
        main_pos = content.index('<main id="main"')

        self.assertLess(body_pos, skip_pos)
        self.assertLess(skip_pos, navbar_pos)
        self.assertLess(skip_pos, main_pos)
        self.assertIn('<a class="skip-link" href="#main">Skip to main content</a>', content)
        self.assertIn("Skip to main content", content[body_pos:main_pos])

    def test_main_element_uses_app_offset_without_inline_padding(self):
        content = self._get_content()
        self.assertIn('<main id="main" class="h-100 app-offset">', content)
        self.assertNotIn("padding-top: 64px", content)

    def test_navbar_is_collapsible_with_toggler_attributes(self):
        content = self._get_content()
        self.assertIn("navbar-expand-lg", content)
        self.assertNotIn("fixed-top", content)
        self.assertIn('class="collapse navbar-collapse" id="appNavbar"', content)
        self.assertIn('data-toggle="collapse"', content)
        self.assertIn('data-target="#appNavbar"', content)
        self.assertIn('aria-controls="appNavbar"', content)
        self.assertIn('aria-expanded="false"', content)
        self.assertIn('aria-label="Toggle navigation menu"', content)

        nav_region = content[: content.index('<main id="main"')]
        collapse_start = nav_region.index('id="appNavbar"')
        wrapper = nav_region[nav_region.rindex("<div", 0, collapse_start) : nav_region.index("</nav>")]
        self.assertEqual(wrapper.count("<ul "), 2)
        last_ul_close = wrapper.rindex("</ul>")
        wrapper_close = wrapper.index("</div>")
        self.assertGreater(wrapper_close, last_ul_close)

    def test_authenticated_nav_lists_ordered_inside_collapse_wrapper(self):
        content = self._get_content()
        nav_region = content[: content.index('<main id="main"')]
        collapse_start = nav_region.index('id="appNavbar"')

        markers = [
            'href="/gwflow/"',
            "gwcloud-python.readthedocs.io",
            'href="/api-token/"',
            'href="/sso/logout/"',
        ]
        positions = [nav_region.index(marker) for marker in markers]
        for position in positions:
            self.assertGreater(position, collapse_start)
        self.assertEqual(positions, sorted(positions))

    def test_gwflow_link_has_aria_current_on_resolved_url(self):
        content = self._get_content()
        gwflow_anchor = self._anchor_containing(content, 'href="/gwflow/"')
        self.assertIn('class="nav-link active"', gwflow_anchor)
        self.assertIn('aria-current="page"', gwflow_anchor)

        python_api_anchor = self._anchor_containing(content, "gwcloud-python.readthedocs.io")
        self.assertNotIn("aria-current", python_api_anchor)
        self.assertNotIn('class="nav-link active"', python_api_anchor)

    def test_anonymous_render_shows_login(self):
        self.deauthenticate()
        with mock.patch(
            "bilbyui.views.list_gwflow_jobs",
            side_effect=empty_gwflow_jobs_side_effect(),
        ):
            response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)
        content = response.content.decode()
        self.assertIn(f'href="{reverse("sso:login")}"', content)
        self.assertIn(">Login</a>", content)
        self.assertNotIn('href="/sso/logout/"', content)
