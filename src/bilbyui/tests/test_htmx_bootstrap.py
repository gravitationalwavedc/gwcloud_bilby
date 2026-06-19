from django.urls import reverse

from bilbyui.tests.testcases import BilbyTestCase


class TestHtmxBootstrap(BilbyTestCase):
    def setUp(self):
        self.health_url = reverse("bilbyui:health")

    def test_health_view_returns_200(self):
        response = self.client.get(self.health_url)
        self.assertEqual(response.status_code, 200)

    def test_health_view_renders_base_template(self):
        response = self.client.get(self.health_url)
        content = response.content.decode()
        self.assertIn("<!doctype html>", content)
        self.assertIn("htmx.min.js", content)

    def test_health_view_renders_alpine_script(self):
        response = self.client.get(self.health_url)
        content = response.content.decode()
        self.assertIn("alpine.min.js", content)

    def test_health_view_renders_jquery_before_bootstrap(self):
        response = self.client.get(self.health_url)
        content = response.content.decode()
        self.assertIn("jquery-3.7.1.min.js", content)
        self.assertIn("bootstrap.bundle.min.js", content)
        self.assertLess(
            content.index("jquery-3.7.1.min.js"),
            content.index("bootstrap.bundle.min.js"),
        )
        self.assertLess(
            content.index("bootstrap.bundle.min.js"),
            content.index("htmx.min.js"),
        )

    def test_navbar_anonymous_shows_login(self):
        response = self.client.get(self.health_url)
        content = response.content.decode()
        login_url = reverse("sso:login")
        self.assertIn(f'href="{login_url}"', content)
        self.assertIn("Login", content)
        self.assertNotIn("API Tokens", content)
        self.assertNotIn('href="/sso/logout/"', content)

    def test_navbar_authenticated_shows_full_menu(self):
        self.authenticate()
        response = self.client.get(self.health_url)
        content = response.content.decode()
        login_url = reverse("sso:login")
        self.assertIn("Python API", content)
        self.assertIn("API Tokens", content)
        self.assertIn(self.DEFAULT_USER["name"], content)
        self.assertIn('href="/sso/logout/"', content)
        self.assertNotIn(f'href="{login_url}"', content)
        self.assertIn("bi-code", content)
        self.assertIn("bi-key", content)
        self.assertIn("bi-person", content)
        self.assertIn("bi-box-arrow-right", content)

    def test_navbar_anonymous_has_no_auth_icons(self):
        response = self.client.get(self.health_url)
        content = response.content.decode()
        self.assertNotIn("bi-code", content)
        self.assertNotIn("bi-box-arrow-right", content)

    def test_base_template_includes_bootstrap_icons(self):
        response = self.client.get(self.health_url)
        content = response.content.decode()
        self.assertIn("bootstrap-icons.min.css", content)

    def test_navbar_logo_links_home(self):
        response = self.client.get(self.health_url)
        content = response.content.decode()
        self.assertIn('class="navbar-brand navbar-brand-link mr-auto" href="/"', content)

    def test_navbar_api_tokens_link(self):
        self.authenticate()
        response = self.client.get(self.health_url)
        content = response.content.decode()
        self.assertIn('href="/api-token/"', content)

    def test_google_analytics_absent_when_disabled(self):
        response = self.client.get(self.health_url)
        content = response.content.decode()
        self.assertNotIn("googletagmanager.com", content)
        self.assertNotIn("UA-219714075-1", content)
