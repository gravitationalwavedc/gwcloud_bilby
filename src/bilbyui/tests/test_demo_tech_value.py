from django.conf import settings
from django.urls import reverse

from bilbyui.tests.testcases import BilbyTestCase


def long_path(target):
    """Rebuild the hardcoded stress paths from demo_tech_value.html deterministically.

    prefix + dataNNN/ segments + a filler-padded filename lands on exactly
    `target` characters, mirroring how the fixture literals were generated.
    """
    prefix = "/home/lewis.cit/cbc/o4a/S230601ag/pe-runs/"
    suffix = "posterior_samples.h5"
    segments = []
    current = len(prefix)
    index = 0
    while True:
        segment = f"data{index:03d}/"
        if current + len(segment) > target - len(suffix):
            break
        segments.append(segment)
        current += len(segment)
        index += 1
    filler = "x" * (target - current - len(suffix))
    filename = f"posterior_samples{filler}.h5" if filler else suffix
    return prefix + "".join(segments) + filename


class TestTechValueDemoPage(BilbyTestCase):
    url = "/demo/tech-value/"

    def setUp(self):
        self.deauthenticate()

    def test_url_resolves_to_demo_route(self):
        self.assertEqual(reverse("bilbyui:tech_value_demo"), self.url)

    def test_anonymous_get_redirects_to_login(self):
        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response["Location"], f"{settings.LOGIN_URL}?next={self.url}")

    def test_authenticated_get_returns_200(self):
        self.authenticate()

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)

    def test_renders_all_component_variants(self):
        self.authenticate()

        response = self.client.get(self.url)

        content = response.content.decode()
        # Identifier mode (superevent + SHA) and truncated variant both present
        self.assertContains(response, "tech-value--id")
        self.assertContains(response, "tech-value--truncated")
        # 10 includes: compact + truncated + 2 ids + 4 stress + 2 hostile
        full_blocks = content.count('class="tech-value-full"')
        self.assertGreaterEqual(full_blocks, 10)

    def test_hostile_input_rendered_escaped(self):
        self.authenticate()

        response = self.client.get(self.url)

        content = response.content.decode()
        # Injected payload must be escaped, never emitted as a live script element
        self.assertIn("&lt;script&gt;alert(1)&lt;/script&gt;", content)
        self.assertNotIn("<script>alert", content)
        # Quote-heavy value survives autoescaping without breaking markup
        self.assertIn("O&#x27;Brien &quot;quoted&quot; path/x.h5", content)

    def test_stress_paths_rendered_in_full(self):
        self.authenticate()

        response = self.client.get(self.url)

        content = response.content.decode()
        path_500 = long_path(500)
        path_1000 = long_path(1000)
        self.assertEqual(len(path_500), 500)
        self.assertEqual(len(path_1000), 1000)
        self.assertIn(path_500, content)
        self.assertIn(path_1000, content)

    def test_copy_labels_rendered(self):
        self.authenticate()

        response = self.client.get(self.url)

        self.assertContains(response, "Copy superevent ID")

    def test_analysis_uid_copy_label_rendered(self):
        self.authenticate()

        response = self.client.get(self.url)

        # The UID fixture's copy button must expose "Copy analysis UID" as its
        # accessible name (the component renders copy_label as button text).
        self.assertContains(response, "Copy analysis UID")
