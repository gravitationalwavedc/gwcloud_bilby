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
