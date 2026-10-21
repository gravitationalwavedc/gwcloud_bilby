import json
from pathlib import Path
from unittest import mock

from adacs_sso_plugin.constants import AUTHENTICATION_METHODS
from django.http import Http404
from django.test import RequestFactory, override_settings
from django.urls import reverse

from bilbyui.models import GWFlowJob
from bilbyui.services.gwflow_versions import adapt_semantic_diff
from bilbyui.tests.testcases import BilbyTestCase
from bilbyui.views import _render_gwflow_history_section


def _create_job(user, sname="S230601ag", **kwargs):
    defaults = {
        "sname": sname,
        "user": user,
        "libraries": ["cbc-workflow-o4a"],
    }
    defaults.update(kwargs)
    return GWFlowJob.objects.create(**defaults)


class TestGWFlowDetailZeroHistoryRequests(BilbyTestCase):
    def setUp(self):
        self.ligo_user = self.create_user(
            id=10,
            authentication_method=AUTHENTICATION_METHODS["LIGO_SHIBBOLETH"],
        )
        self.authenticate(user=self.ligo_user)
        self.job = _create_job(self.ligo_user)

    @mock.patch("bilbyui.views.get_versions")
    @mock.patch("bilbyui.views.get_version")
    @mock.patch("bilbyui.views.get_superevent", return_value=({}, "live"))
    def test_detail_page_makes_zero_history_portal_requests(
        self,
        mock_get_superevent,
        mock_get_version,
        mock_get_versions,
    ):
        # The base URL redirects to the metadata section; the metadata pane must
        # not trigger any history portal requests.
        response = self.client.get(
            reverse("bilbyui:gwflow_job_detail", args=[self.job.sname]),
            follow=True,
        )

        self.assertEqual(response.status_code, 200)
        mock_get_versions.assert_not_called()
        mock_get_version.assert_not_called()
        self.assertContains(
            response,
            f'href="{reverse("bilbyui:gwflow_job_history", args=[self.job.sname])}"',
        )
        self.assertNotContains(response, 'id="history-pane"')


class TestGWFlowJobHistoryPartial(BilbyTestCase):
    def setUp(self):
        self.ligo_user = self.create_user(
            id=10,
            authentication_method=AUTHENTICATION_METHODS["LIGO_SHIBBOLETH"],
        )
        self.authenticate(user=self.ligo_user)
        self.job = _create_job(
            self.ligo_user,
            current_history_id="1111222233334444555566667777888899990000",
        )
        self.url = reverse("bilbyui:gwflow_job_history", args=[self.job.sname])
        self.get_version_patcher = mock.patch(
            "bilbyui.views.get_version",
            return_value=({"raw_payload": {}}, "live"),
        )
        self.get_version_patcher.start()
        self.addCleanup(self.get_version_patcher.stop)

    @mock.patch(
        "bilbyui.views.get_versions",
        return_value=(
            [
                {
                    "commit_sha": "1111222233334444555566667777888899990000",
                    "version_number": 1010,
                    "record_timestamp": "2026-08-10 12:00:00 UTC",
                    "is_current": True,
                },
                {
                    "commit_sha": "aaaabbbbccccddddeeeeffff0000111122223333",
                    "version_number": 1011,
                    "record_timestamp": "2026-08-09 10:00:00 UTC",
                    "is_current": False,
                },
            ],
            "live",
        ),
    )
    def test_timeline_rendering_live_versions_with_current_marker(self, mock_get_versions):
        response = self.client.get(self.url, HTTP_HX_REQUEST="true")

        self.assertEqual(response.status_code, 200)
        mock_get_versions.assert_called_once_with(self.job.sname)
        # Short SHAs
        self.assertContains(response, "11112222")
        self.assertContains(response, "aaaabbbb")
        # Timestamps
        self.assertContains(response, "2026-08-10 12:00:00 UTC")
        self.assertContains(response, "2026-08-09 10:00:00 UTC")
        # Current badge
        self.assertContains(response, '<span class="badge badge-primary">Current</span>')
        # Canonical history links use query-backed selection and comparison.
        history_url = reverse("bilbyui:gwflow_job_history", args=[self.job.sname])
        self.assertContains(
            response,
            f'hx-get="{history_url}?version=1111222233334444555566667777888899990000&amp;compare=prev"',
        )
        self.assertContains(
            response,
            f'hx-get="{history_url}?version=aaaabbbbccccddddeeeeffff0000111122223333&amp;compare=prev"',
        )
        self.assertContains(response, 'hx-target="#gwflow-history-region"')
        self.assertContains(response, 'id="gwflow-history-version"')
        self.assertNotContains(response, "Showing cached copy")
        self.assertNotContains(response, "<!doctype html>")

    @mock.patch(
        "bilbyui.views.get_versions",
        return_value=(
            [
                {
                    "commit_sha": "aaaabbbbccccddddeeeeffff0000111122223333",
                    "version_number": 1012,
                    "record_timestamp": "2026-08-09 10:00:00 UTC",
                    "is_current": True,
                }
            ],
            "live",
        ),
    )
    def test_current_marker_fallback_to_is_current(self, mock_get_versions):
        # Job has no current_history_id set
        job = _create_job(self.ligo_user, sname="S230602ag", current_history_id="")
        url = reverse("bilbyui:gwflow_job_history", args=[job.sname])

        response = self.client.get(url, HTTP_HX_REQUEST="true")

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, '<span class="badge badge-primary">Current</span>')

    @mock.patch(
        "bilbyui.views.get_versions",
        return_value=(
            [
                {
                    "commit_sha": "1111222233334444555566667777888899990000",
                    "version_number": 1013,
                    "record_timestamp": "2026-08-10 12:00:00 UTC",
                }
            ],
            "stale",
        ),
    )
    def test_stale_timeline_shows_context_strip_notice(self, mock_get_versions):
        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "The cached copy of the current version is shown.")
        self.assertContains(response, "Refresh")
        self.assertContains(response, 'class="async-notice"')

    @mock.patch("bilbyui.views.get_versions", return_value=(None, "down"))
    def test_down_renders_error_state_with_history_retry(self, mock_get_versions):
        response = self.client.get(self.url, HTTP_HX_REQUEST="true")

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "async-error")
        self.assertContains(response, 'role="alert"')
        self.assertContains(response, '<span class="sr-only">Error:</span>')
        self.assertContains(
            response,
            "Couldn't load the history because the service is temporarily unavailable.",
        )
        self.assertContains(
            response,
            f'hx-get="{reverse("bilbyui:gwflow_job_history", args=[self.job.sname])}"',
        )
        self.assertContains(response, 'hx-target="#detail-pane"')
        self.assertContains(response, "Retry")
        self.assertNotContains(response, "<!doctype html>")
        self.assertEqual(response.content.decode().count('role="alert"'), 1)

    @mock.patch("bilbyui.views.get_versions", return_value=([], "live"))
    def test_empty_versions_list(self, mock_get_versions):
        response = self.client.get(self.url, HTTP_HX_REQUEST="true")

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "No version history is available for this record.")
        self.assertContains(response, 'id="gwflow-history-version"')


class TestGWFlowJobHistoryVersionPartial(BilbyTestCase):
    def setUp(self):
        self.ligo_user = self.create_user(
            id=10,
            authentication_method=AUTHENTICATION_METHODS["LIGO_SHIBBOLETH"],
        )
        self.authenticate(user=self.ligo_user)
        self.job = _create_job(self.ligo_user)
        self.sha = "1111222233334444555566667777888899990000"
        self.url = reverse("bilbyui:gwflow_job_history_version", args=[self.job.sname, self.sha])
        self.get_versions_patcher = mock.patch(
            "bilbyui.views.get_versions",
            return_value=(
                [{"commit_sha": self.sha, "version_number": 1008}],
                "live",
            ),
        )
        self.get_versions_patcher.start()
        self.addCleanup(self.get_versions_patcher.stop)

    @mock.patch(
        "bilbyui.views.get_version",
        return_value=(
            {
                "commit_sha": "1111222233334444555566667777888899990000",
                "version_number": 1008,
                "record_timestamp": "2026-08-10 12:00:00 UTC",
                "gracedb": {"events": [{"uid": "E99", "pipeline": "pycbc"}]},
            },
            "live",
        ),
    )
    def test_live_version_renders_metadata_payload(self, mock_get_version):
        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)
        mock_get_version.assert_called_once_with(self.job.sname, self.sha)
        self.assertContains(response, "11112222")
        self.assertContains(response, "E99")
        self.assertContains(response, "pycbc")
        self.assertContains(response, "Viewing version 11112222 (historical) — not the current record")
        self.assertNotContains(response, "Showing cached copy")
        self.assertNotContains(response, "<!doctype html>")

    @mock.patch(
        "bilbyui.views.get_version",
        return_value=(
            {
                "commit_sha": "1111222233334444555566667777888899990000",
                "version_number": 1009,
                "gracedb": {"events": [{"uid": "E99", "pipeline": "pycbc"}]},
            },
            "stale",
        ),
    )
    def test_stale_version_renders_payload_without_cached_notice(self, mock_get_version):
        # The stale notice now lives in the full-page context strip; the version
        # fragment renders the payload without a duplicate cached-copy note.
        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "E99")
        self.assertContains(response, "pycbc")
        self.assertContains(response, "Viewing version 11112222 (historical) — not the current record")
        self.assertNotContains(response, "Showing cached copy")
        self.assertNotContains(response, "<!doctype html>")

    @mock.patch("bilbyui.views.get_version", return_value=(None, "down"))
    def test_down_renders_error_state_with_version_retry(self, mock_get_version):
        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "async-error")
        self.assertContains(response, 'role="alert"')
        self.assertContains(response, '<span class="sr-only">Error:</span>')
        self.assertContains(
            response,
            "Couldn't load the version details because the service is temporarily unavailable.",
        )
        self.assertContains(
            response,
            f'hx-get="{reverse("bilbyui:gwflow_job_history_version", args=[self.job.sname, self.sha])}"',
        )
        self.assertContains(response, 'hx-target="#gwflow-history-version"')
        self.assertContains(response, "Retry")
        self.assertNotContains(response, "<!doctype html>")
        self.assertEqual(response.content.decode().count('role="alert"'), 1)

    @mock.patch("bilbyui.views.get_version", return_value=(None, "live"))
    def test_missing_version_raises_404(self, mock_get_version):
        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 404)


@override_settings(EMBARGO_START_TIME=100.0)
class TestGWFlowHistoryVisibility(BilbyTestCase):
    def setUp(self):
        self.ligo_user = self.create_user(
            id=10,
            authentication_method=AUTHENTICATION_METHODS["LIGO_SHIBBOLETH"],
        )
        self.non_ligo_user = self.create_user(id=11)
        self.embargoed_job = _create_job(
            self.ligo_user,
            sname="S230601ag",
            trigger_time=100.0,
        )
        self.public_job = _create_job(
            self.ligo_user,
            sname="S230602ag",
            trigger_time=99.0,
        )
        self.sha = "1111222233334444555566667777888899990000"

    def _history_routes(self, sname):
        return [
            reverse("bilbyui:gwflow_job_history", args=[sname]),
            reverse(
                "bilbyui:gwflow_job_history_version",
                args=[sname, self.sha],
            ),
        ]

    def _assert_denied_without_portal_calls(self):
        with (
            mock.patch("bilbyui.views.get_versions") as get_versions,
            mock.patch("bilbyui.views.get_version") as get_version,
            mock.patch("bilbyui.views.get_diff") as get_diff,
        ):
            for url in self._history_routes(self.embargoed_job.sname):
                denied = self.client.get(url)
                missing = self.client.get(url.replace(self.embargoed_job.sname, "S999999zz"))
                self.assertEqual(denied.status_code, 404)
                self.assertEqual(
                    (denied.status_code, denied.content, sorted(denied.headers.items())),
                    (missing.status_code, missing.content, sorted(missing.headers.items())),
                )
            get_versions.assert_not_called()
            get_version.assert_not_called()
            get_diff.assert_not_called()

    def test_anonymous_denied_matches_missing_and_makes_zero_portal_calls(self):
        self.deauthenticate()
        self._assert_denied_without_portal_calls()

    def test_non_ligo_denied_matches_missing_and_makes_zero_portal_calls(self):
        self.authenticate(user=self.non_ligo_user)
        self._assert_denied_without_portal_calls()

    @mock.patch(
        "bilbyui.views.get_versions",
        return_value=([{"commit_sha": "1111222233334444555566667777888899990000", "version_number": 1010}], "live"),
    )
    @mock.patch("bilbyui.views.get_version", return_value=({}, "live"))
    def test_ligo_user_200_on_all_history_routes(
        self,
        mock_get_version,
        mock_get_versions,
    ):
        self.authenticate(user=self.ligo_user)
        for url in self._history_routes(self.embargoed_job.sname):
            self.assertEqual(self.client.get(url).status_code, 200)

    @mock.patch(
        "bilbyui.views.get_versions",
        return_value=([{"commit_sha": "1111222233334444555566667777888899990000", "version_number": 1011}], "live"),
    )
    @mock.patch("bilbyui.views.get_version", return_value=({}, "live"))
    def test_legacy_flag_does_not_hide_public_history(
        self,
        mock_get_version,
        mock_get_versions,
    ):
        self.authenticate(user=self.non_ligo_user)
        for url in self._history_routes(self.public_job.sname):
            self.assertEqual(self.client.get(url).status_code, 200)

    def test_missing_job_history_404(self):
        self.authenticate(user=self.ligo_user)
        for url in self._history_routes("S999999zz"):
            self.assertEqual(self.client.get(url).status_code, 404)


@override_settings(IGNORE_ELASTIC_SEARCH=True)
class TestRenderGWFlowHistorySection(BilbyTestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.sname = "S230601ag"
        self.current_sha = "aaaabbbbccccddddeeeeffff0000111122223333"
        self.previous_sha = "1111222233334444555566667777888899990000"
        self.oldest_sha = "0000000000000000000000000000000000000000"
        self.request = self.factory.get(reverse("bilbyui:gwflow_job_history", args=[self.sname]))

        self.get_version_patcher = mock.patch(
            "bilbyui.views.get_version",
            return_value=({"raw_payload": {}}, "live"),
        )
        self.mock_get_version = self.get_version_patcher.start()
        self.addCleanup(self.get_version_patcher.stop)

        self.get_diff_patcher = mock.patch(
            "bilbyui.views.get_diff",
            return_value=(self._semantic_payload(), "live"),
        )
        self.mock_get_diff = self.get_diff_patcher.start()
        self.addCleanup(self.get_diff_patcher.stop)

    def _job(self):
        job = mock.Mock()
        job.current_history_id = self.current_sha
        return job

    def _metadata_versions(self):
        return [
            {
                "commit_sha": self.oldest_sha,
                "version_number": 1005,
                "record_timestamp": "2026-08-08 10:00:00 UTC",
                "is_current": False,
            },
            {
                "commit_sha": self.previous_sha,
                "version_number": 1006,
                "record_timestamp": "2026-08-09 10:00:00 UTC",
                "is_current": False,
            },
            {
                "commit_sha": self.current_sha,
                "version_number": 1007,
                "record_timestamp": "2026-08-10 10:00:00 UTC",
                "is_current": True,
            },
        ]

    def _semantic_payload(
        self,
        *,
        baseline_version=1006,
        selected_version=1007,
        changes=None,
    ):
        if changes is None:
            changes = [
                {
                    "entity_type": "analysis",
                    "identity": "analysis-1",
                    "kind": "modified",
                    "before": {"status": "draft"},
                    "after": {"status": "ready"},
                    "field_diffs": {
                        "status": {
                            "baseline": "draft",
                            "selected": "ready",
                        }
                    },
                }
            ]
        return {
            "sname": self.sname,
            "baseline_version": baseline_version,
            "selected_version": selected_version,
            "baseline_timestamp": "2026-08-09T10:00:00+00:00",
            "selected_timestamp": "2026-08-10T10:00:00+00:00",
            "changes": changes,
        }

    def _render(
        self,
        *,
        versions=None,
        versions_state="live",
        request=None,
        job=None,
    ):
        with (
            mock.patch(
                "bilbyui.views._get_gwflow_job_or_404",
                return_value=job or self._job(),
            ),
            mock.patch(
                "bilbyui.views.get_versions",
                return_value=(
                    self._metadata_versions() if versions is None else versions,
                    versions_state,
                ),
            ),
        ):
            return _render_gwflow_history_section(
                request or self.request,
                self.sname,
            )

    @mock.patch("bilbyui.views._get_gwflow_job_or_404", return_value=mock.Mock())
    @mock.patch("bilbyui.views.get_versions", return_value=(None, "down"))
    def test_down_state_renders_error_with_history_retry(
        self,
        mock_get_versions,
        mock_get_job,
    ):
        response, stale = _render_gwflow_history_section(
            self.request,
            self.sname,
        )

        self.assertFalse(stale)
        response.render()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.template_name, "bilbyui/_async_state.html")
        self.assertContains(response, "async-error")
        self.assertContains(
            response,
            "Couldn't load the history because the service is temporarily unavailable.",
        )
        self.assertContains(
            response,
            f'hx-get="{reverse("bilbyui:gwflow_job_history", args=[self.sname])}"',
        )
        self.assertContains(response, 'hx-target="#detail-pane"')
        self.mock_get_version.assert_not_called()
        self.mock_get_diff.assert_not_called()

    @mock.patch("bilbyui.views._get_gwflow_job_or_404", return_value=mock.Mock())
    @mock.patch("bilbyui.views.get_versions", return_value=(None, "live"))
    def test_none_versions_renders_error_with_history_retry(
        self,
        mock_get_versions,
        mock_get_job,
    ):
        response, stale = _render_gwflow_history_section(
            self.request,
            self.sname,
        )

        self.assertFalse(stale)
        response.render()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.template_name, "bilbyui/_async_state.html")
        self.assertContains(response, "async-error")
        self.assertContains(
            response,
            f'hx-get="{reverse("bilbyui:gwflow_job_history", args=[self.sname])}"',
        )

    @mock.patch("bilbyui.views._get_gwflow_job_or_404", return_value=mock.Mock())
    @mock.patch("bilbyui.views.get_versions", return_value=(None, "failed"))
    def test_failed_versions_raise_404(
        self,
        mock_get_versions,
        mock_get_job,
    ):
        with self.assertRaisesMessage(Http404, "History not found"):
            _render_gwflow_history_section(self.request, self.sname)

    def test_no_baseline_makes_zero_diff_calls(self):
        versions = [self._metadata_versions()[0]]
        job = self._job()
        job.current_history_id = self.oldest_sha

        response, stale = self._render(versions=versions, job=job)

        self.assertFalse(stale)
        self.mock_get_diff.assert_not_called()
        self.mock_get_version.assert_called_once_with(self.sname, 1005)
        self.assertEqual(
            response.context_data["diff_outcome"].status,
            "no_baseline",
        )

    def test_semantic_rows_exposed_in_context(self):
        response, stale = self._render()

        self.assertFalse(stale)
        outcome = response.context_data["diff_outcome"]
        self.assertEqual(outcome.status, "semantic")
        self.assertEqual(len(outcome.rows), 1)
        self.assertEqual(outcome.rows[0].entity_type, "analysis")
        self.assertEqual(outcome.rows[0].identity, "analysis-1")
        self.assertEqual(outcome.rows[0].kind, "modified")
        self.mock_get_diff.assert_called_once_with(self.sname, 1006, 1007)

    def test_diff_rows_are_shaped_by_kind(self):
        cases = (
            (
                "added",
                {
                    "entity_type": "analysis",
                    "identity": "analysis-added",
                    "kind": "added",
                    "before": None,
                    "after": {"status": "ready"},
                    "field_diffs": {},
                },
                {
                    "record": {"status": "ready"},
                    "field_diffs": {},
                    "field_diff_count": 0,
                },
            ),
            (
                "removed",
                {
                    "entity_type": "analysis",
                    "identity": "analysis-removed",
                    "kind": "removed",
                    "before": {"status": "ready"},
                    "after": None,
                    "field_diffs": {},
                },
                {
                    "record": {"status": "ready"},
                    "field_diffs": {},
                    "field_diff_count": 0,
                },
            ),
            (
                "modified",
                {
                    "entity_type": "analysis",
                    "identity": "analysis-modified",
                    "kind": "modified",
                    "before": {"status": "draft"},
                    "after": {"status": "ready"},
                    "field_diffs": {
                        "status": {
                            "baseline": "draft",
                            "selected": "ready",
                        }
                    },
                },
                {
                    "record": None,
                    "field_diffs": {
                        "status": {
                            "baseline": "draft",
                            "selected": "ready",
                        }
                    },
                    "field_diff_count": 1,
                },
            ),
            (
                "deprecated",
                {
                    "entity_type": "analysis",
                    "identity": "analysis-deprecated",
                    "kind": "deprecated",
                    "before": {"deprecated": False},
                    "after": {"deprecated": True},
                    "field_diffs": {
                        "deprecated": {
                            "baseline": False,
                            "selected": True,
                        }
                    },
                },
                {
                    "record": (
                        {"deprecated": False},
                        {"deprecated": True},
                    ),
                    "field_diffs": {
                        "deprecated": {
                            "baseline": False,
                            "selected": True,
                        }
                    },
                    "field_diff_count": 1,
                },
            ),
        )

        expected_keys = {
            "entity_type",
            "kind",
            "identity_primary",
            "identity_value",
            "field_diff_count",
            "record",
            "field_diffs",
        }
        for name, change, expected in cases:
            with self.subTest(kind=name):
                self.mock_get_diff.return_value = (
                    self._semantic_payload(changes=[change]),
                    "live",
                )

                response, _ = self._render()

                row = response.context_data["diff_rows"][0]
                self.assertEqual(set(row), expected_keys)
                self.assertEqual(row["entity_type"], "analysis")
                self.assertEqual(row["kind"], name)
                self.assertEqual(row["identity_primary"], change["identity"])
                self.assertEqual(row["identity_value"], change["identity"])
                self.assertEqual(row["record"], expected["record"])
                self.assertEqual(row["field_diffs"], expected["field_diffs"])
                self.assertEqual(
                    row["field_diff_count"],
                    expected["field_diff_count"],
                )

    def test_review_identity_is_shaped_for_display_and_copy(self):
        occurrence_uid = "review-occurrence-1"
        review_record = {
            "occurrence_uid": occurrence_uid,
            "name": "Review",
            "description": "Review description",
            "reviewers": [],
            "passed_review": None,
            "completion_date": None,
            "review_status": "pending",
        }
        self.mock_get_diff.return_value = (
            self._semantic_payload(
                changes=[
                    {
                        "entity_type": "review",
                        "identity": {
                            "analysis_uid": "pe_1",
                            "occurrence_uid": occurrence_uid,
                        },
                        "kind": "modified",
                        "before": review_record,
                        "after": review_record,
                        "field_diffs": {},
                    }
                ]
            ),
            "live",
        )

        response, _ = self._render()

        row = response.context_data["diff_rows"][0]
        self.assertEqual(
            row["identity_primary"],
            "pe_1 / review-occurrence-1",
        )
        self.assertEqual(row["identity_value"], row["identity_primary"])

    def test_diff_announcement_matches_each_outcome_status(self):
        cases = (
            (
                "semantic_singular",
                self._semantic_payload(),
                "live",
                None,
                "1 semantic change.",
            ),
            (
                "semantic_plural",
                self._semantic_payload(
                    changes=[
                        {
                            "entity_type": "analysis",
                            "identity": identity,
                            "kind": "modified",
                            "before": {"status": "draft"},
                            "after": {"status": "ready"},
                            "field_diffs": {
                                "status": {
                                    "baseline": "draft",
                                    "selected": "ready",
                                }
                            },
                        }
                        for identity in ("analysis-1", "analysis-2")
                    ]
                ),
                "live",
                None,
                "2 semantic changes.",
            ),
            (
                "semantic_empty",
                self._semantic_payload(changes=[]),
                "live",
                None,
                "No semantic changes.",
            ),
            (
                "no_baseline",
                None,
                "live",
                [self._metadata_versions()[0]],
                "No earlier version available to compare.",
            ),
            (
                "unavailable",
                None,
                "down",
                None,
                "Semantic comparison unavailable.",
            ),
            (
                "failed",
                None,
                "failed",
                None,
                "Semantic comparison failed.",
            ),
        )

        for name, payload, state, versions, expected in cases:
            with self.subTest(status=name):
                self.mock_get_diff.reset_mock()
                self.mock_get_diff.return_value = (payload, state)
                job = None
                if versions is not None:
                    job = self._job()
                    job.current_history_id = self.oldest_sha

                response, _ = self._render(versions=versions, job=job)

                self.assertEqual(
                    response.context_data["diff_announcement"],
                    expected,
                )

    def test_deprecated_kind_never_reaches_template_for_non_analysis(self):
        for entity_type in (
            "detector_configuration",
            "gracedb_event",
            "catalog_connection",
            "review",
        ):
            with self.subTest(entity_type=entity_type):
                identity = (
                    {
                        "analysis_uid": "pe_1",
                        "occurrence_uid": "review-occurrence-1",
                    }
                    if entity_type == "review"
                    else "identity-1"
                )
                outcome = adapt_semantic_diff(
                    sname=self.sname,
                    baseline_version=1006,
                    selected_version=1007,
                    payload=self._semantic_payload(
                        changes=[
                            {
                                "entity_type": entity_type,
                                "identity": identity,
                                "kind": "deprecated",
                                "before": {},
                                "after": {},
                                "field_diffs": {},
                            }
                        ]
                    ),
                    state="live",
                )

                self.assertEqual(outcome.status, "failed")
                self.assertEqual(outcome.rows, ())
                self.assertEqual(
                    outcome.reason,
                    "invalid_enum:changes[0].kind",
                )

    def test_semantic_empty_distinct_from_no_baseline(self):
        self.mock_get_diff.return_value = (
            self._semantic_payload(changes=[]),
            "live",
        )

        response, _ = self._render()

        outcome = response.context_data["diff_outcome"]
        self.assertEqual(outcome.status, "semantic_empty")
        self.assertEqual(outcome.rows, ())

    def test_unavailable_exposes_retry_state(self):
        self.mock_get_diff.return_value = (None, "down")

        response, _ = self._render()

        outcome = response.context_data["diff_outcome"]
        self.assertEqual(outcome.status, "unavailable")
        self.assertEqual(outcome.reason, "service_unavailable")

    def test_failed_status_never_renders_as_empty(self):
        self.mock_get_diff.return_value = (None, "failed")

        response, _ = self._render()

        outcome = response.context_data["diff_outcome"]
        self.assertEqual(outcome.status, "failed")
        self.assertNotEqual(outcome.status, "semantic_empty")
        self.assertEqual(outcome.rows, ())

    def test_malformed_portal_payload_maps_to_failed(self):
        self.mock_get_diff.return_value = (
            {"changes": []},
            "live",
        )

        response, _ = self._render()

        outcome = response.context_data["diff_outcome"]
        self.assertEqual(outcome.status, "failed")
        self.assertEqual(outcome.reason, "invalid_keys:root")
        self.assertEqual(outcome.rows, ())

    def test_stale_combined_from_versions_selected_detail_and_diff(self):
        cases = [
            ("all_fresh", "live", "live", "live", False),
            ("versions", "stale", "live", "live", True),
            ("selected_detail", "live", "stale", "live", True),
            ("diff", "live", "live", "stale", True),
            ("versions_selected", "stale", "stale", "live", True),
            ("versions_diff", "stale", "live", "stale", True),
            ("selected_diff", "live", "stale", "stale", True),
            ("all_three", "stale", "stale", "stale", True),
        ]

        for name, versions_state, selected_state, diff_state, expected in cases:
            with self.subTest(name=name):
                self.mock_get_version.reset_mock()
                self.mock_get_diff.reset_mock()
                self.mock_get_version.return_value = (
                    {"raw_payload": {}},
                    selected_state,
                )
                self.mock_get_diff.return_value = (
                    self._semantic_payload(),
                    diff_state,
                )

                response, stale = self._render(
                    versions_state=versions_state,
                )

                self.assertEqual(stale, expected)
                self.assertEqual(response.context_data["stale"], expected)

    def test_selected_detail_failure_keeps_semantic_rows(self):
        self.mock_get_version.return_value = (None, "down")

        response, stale = self._render()

        self.assertFalse(stale)
        self.assertIsNone(response.context_data["presentation"])
        self.mock_get_version.assert_called_once_with(self.sname, 1007)
        self.mock_get_diff.assert_called_once_with(self.sname, 1006, 1007)
        outcome = response.context_data["diff_outcome"]
        self.assertEqual(outcome.status, "semantic")
        self.assertEqual(len(outcome.rows), 1)

    def test_reversed_current_direction_preserved(self):
        request = self.factory.get(
            reverse("bilbyui:gwflow_job_history", args=[self.sname]),
            {
                "version": self.previous_sha,
                "compare": "current",
            },
        )
        self.mock_get_diff.return_value = (
            self._semantic_payload(
                baseline_version=1007,
                selected_version=1006,
            ),
            "live",
        )

        response, _ = self._render(request=request)

        self.mock_get_diff.assert_called_once_with(self.sname, 1007, 1006)
        outcome = response.context_data["diff_outcome"]
        self.assertEqual(outcome.baseline_version, 1007)
        self.assertEqual(outcome.selected_version, 1006)

    def test_history_render_has_no_raw_json_context(self):
        response, _ = self._render()
        response.render()
        content = response.content.decode()

        self.assertNotIn("baseline_raw_json", response.context_data)
        self.assertNotIn("selected_raw_json", response.context_data)
        self.assertNotIn("baseline_presentation", response.context_data)
        self.assertNotIn("<pre><code>", content)
        self.assertNotIn("Temporary technical inspection aid", content)

    def test_unknown_version_deep_link_raises_404(self):
        request = self.factory.get(
            reverse("bilbyui:gwflow_job_history", args=[self.sname]),
            {"version": "ffffffffffffffffffffffffffffffffffffffff"},
        )

        with self.assertRaisesMessage(Http404, "Version not found"):
            self._render(request=request)

        self.mock_get_version.assert_not_called()
        self.mock_get_diff.assert_not_called()

    def test_malformed_summary_renders_error_state_with_retry(self):
        malformed = [
            {
                "commit_sha": self.current_sha,
                "version_number": "1007",
                "record_timestamp": "2026-08-10 10:00:00 UTC",
                "is_current": True,
            }
        ]

        with self.assertLogs("bilbyui.views", level="WARNING") as logs:
            response, stale = self._render(
                versions=malformed,
                versions_state="stale",
            )

        self.assertFalse(stale)
        response.render()
        self.assertEqual(response.template_name, "bilbyui/_async_state.html")
        self.assertContains(response, "async-error")
        self.assertContains(
            response,
            f'hx-get="{reverse("bilbyui:gwflow_job_history", args=[self.sname])}"',
        )
        self.assertContains(response, 'hx-target="#detail-pane"')
        self.assertTrue(any(self.sname in message and "ValueError" in message for message in logs.output))
        self.mock_get_version.assert_not_called()
        self.mock_get_diff.assert_not_called()

    def test_selected_detail_fetched_once_by_version_number(self):
        self._render()

        self.mock_get_version.assert_called_once_with(self.sname, 1007)

    def test_live_render_returns_history_template(self):
        response, stale = self._render()

        self.assertFalse(stale)
        self.assertEqual(
            response.template_name,
            "bilbyui/_gwflow_history.html",
        )
        self.assertEqual(response.context_data["selected_version"].full_sha, self.current_sha)
        self.assertEqual(response.context_data["baseline_version"].full_sha, self.previous_sha)

    def test_selected_payload_still_feeds_metadata_presentation(self):
        self.mock_get_version.return_value = (
            {"raw_payload": {"info": {"status": "ready"}}},
            "live",
        )

        response, _ = self._render()

        self.assertIsNotNone(response.context_data["presentation"])

    def test_non_mapping_selected_detail_has_no_presentation(self):
        self.mock_get_version.return_value = (
            ["not", "a", "mapping"],
            "live",
        )

        response, _ = self._render()

        self.assertIsNone(response.context_data["presentation"])
        self.assertEqual(
            response.context_data["diff_outcome"].status,
            "semantic",
        )


FIXTURE_DIR = Path(__file__).parent / "fixtures" / "gwflow_diff"


@override_settings(IGNORE_ELASTIC_SEARCH=True)
class TestGWFlowHistoryRenderedOutcomes(BilbyTestCase):
    def setUp(self):
        self.user = self.create_user(
            id=90,
            authentication_method=AUTHENTICATION_METHODS["LIGO_SHIBBOLETH"],
        )
        self.authenticate(user=self.user)
        self.sname = "S240101aa"
        self.previous_sha = "1" * 40
        self.current_sha = "2" * 40
        self.job = _create_job(
            self.user,
            sname=self.sname,
            current_history_id=self.current_sha,
        )
        self.url = reverse("bilbyui:gwflow_job_history", args=[self.sname])
        self.versions = [
            {
                "commit_sha": self.previous_sha,
                "version_number": 41,
                "record_timestamp": "2026-09-01 00:00:00 UTC",
                "is_current": False,
            },
            {
                "commit_sha": self.current_sha,
                "version_number": 42,
                "record_timestamp": "2026-09-02 00:00:00 UTC",
                "is_current": True,
            },
        ]

    def semantic_payload(self, *, changes=None):
        if changes is None:
            changes = [
                {
                    "entity_type": "analysis",
                    "identity": "analysis-safe",
                    "kind": "modified",
                    "before": {
                        "nested": {
                            "null_value": None,
                            "false_value": False,
                            "zero_value": 0,
                        }
                    },
                    "after": {
                        "nested": {
                            "null_value": None,
                            "false_value": False,
                            "zero_value": 0,
                        }
                    },
                    "field_diffs": {
                        "nested": {
                            "baseline": {
                                "null_value": None,
                                "false_value": False,
                                "zero_value": 0,
                            },
                            "selected": {
                                "null_value": None,
                                "false_value": False,
                                "zero_value": 0,
                            },
                        }
                    },
                }
            ]
        return {
            "sname": self.sname,
            "baseline_version": 41,
            "selected_version": 42,
            "baseline_timestamp": "2026-09-01T00:00:00Z",
            "selected_timestamp": "2026-09-02T00:00:00Z",
            "changes": changes,
        }

    def render(self, *, versions=None, diff_payload=None, diff_state="live"):
        if versions is None:
            versions = self.versions
        if diff_payload is None and diff_state == "live":
            diff_payload = self.semantic_payload()
        with (
            mock.patch(
                "bilbyui.views.get_versions",
                return_value=(versions, "live"),
            ) as get_versions,
            mock.patch(
                "bilbyui.views.get_version",
                return_value=({"raw_payload": {}}, "live"),
            ) as get_version,
            mock.patch(
                "bilbyui.views.get_diff",
                return_value=(diff_payload, diff_state),
            ) as get_diff,
        ):
            response = self.client.get(self.url, HTTP_HX_REQUEST="true")
        return response, get_versions, get_version, get_diff

    def changes_region(self, response):
        content = response.content.decode()
        marker = '<section class="gwflow-changes"'
        self.assertIn(marker, content)
        return marker + content.split(marker, 1)[1].split("</section>", 1)[0]

    def test_semantic_render_uses_validated_labels_and_structured_values(self):
        response, get_versions, get_version, get_diff = self.render()

        self.assertEqual(response.status_code, 200)
        region = self.changes_region(response)
        self.assertIn("Changes from previous", region)
        self.assertIn("version 41 to selected version 42", region)
        self.assertIn("2026-09-01T00:00:00Z", region)
        self.assertIn("2026-09-02T00:00:00Z", region)
        self.assertIn("1 semantic change.", region)
        row = response.context["diff_rows"][0]
        self.assertIsNone(row["record"])
        self.assertEqual(
            row["field_diffs"]["nested"]["baseline"],
            {
                "null_value": None,
                "false_value": False,
                "zero_value": 0,
            },
        )
        self.assertNotIn("None", region)
        self.assertNotIn("Try again", region)
        get_versions.assert_called_once_with(self.sname)
        get_version.assert_called_once_with(self.sname, 42)
        get_diff.assert_called_once_with(self.sname, 41, 42)

    def load_fixture(self, name):
        with (FIXTURE_DIR / name).open(encoding="utf-8") as fixture:
            payload = json.load(fixture)
        payload["sname"] = self.sname
        payload["baseline_version"] = 41
        payload["selected_version"] = 42
        return payload

    def assert_announcement(self, response, sentence):
        content = " ".join(response.content.decode().split())
        self.assertIn('class="sr-only" role="status" aria-live="polite"', content)
        self.assertIn(sentence, content)

    def test_shared_golden_fixture_renders_entity_and_kind_classes(self):
        response, _, _, _ = self.render(
            diff_payload=self.load_fixture("semantic_diff.json"),
        )
        content = response.content.decode()

        for entity_type in (
            "analysis",
            "detector_configuration",
            "gracedb_event",
            "catalog_connection",
            "review",
        ):
            with self.subTest(entity_type=entity_type):
                self.assertIn(f">{entity_type}</strong>", content)
        for kind in ("added", "removed", "modified", "deprecated"):
            with self.subTest(kind=kind):
                self.assertIn(f"gwflow-change-badge--{kind}", content)
        for identity in (
            "S000001a-validation-report",
            "pe_1",
            "H1",
            "G000001",
            "4:1",
            "pe_1 / review-occurrence-1",
        ):
            with self.subTest(identity=identity):
                self.assertIn(identity, content)
        self.assertGreaterEqual(content.count("tech-value--id"), 6)
        self.assertNotIn("<pre><code>", content)
        self.assertNotIn("Temporary technical inspection aid", content)
        self.assert_announcement(response, "6 semantic changes.")

    def test_all_supported_entity_kind_combinations_render(self):
        response, _, _, _ = self.render(
            diff_payload=self.load_fixture("semantic_diff_all_combinations.json"),
        )
        content = response.content.decode()
        combinations = (
            ("analysis", "added", "01-01-analysis-added"),
            ("analysis", "removed", "01-02-analysis-removed"),
            ("analysis", "modified", "01-03-analysis-modified"),
            ("analysis", "deprecated", "01-04-analysis-deprecated"),
            ("detector_configuration", "added", "02-01-detector_configuration-added"),
            ("detector_configuration", "removed", "02-02-detector_configuration-removed"),
            ("detector_configuration", "modified", "02-03-detector_configuration-modified"),
            ("gracedb_event", "added", "03-01-gracedb_event-added"),
            ("gracedb_event", "removed", "03-02-gracedb_event-removed"),
            ("gracedb_event", "modified", "03-03-gracedb_event-modified"),
            ("catalog_connection", "added", "04-01-catalog_connection-added"),
            ("catalog_connection", "removed", "04-02-catalog_connection-removed"),
            ("catalog_connection", "modified", "04-03-catalog_connection-modified"),
            ("review", "added", "analysis-05 / 05-01-review-added"),
            ("review", "removed", "analysis-05 / 05-02-review-removed"),
            ("review", "modified", "analysis-05 / 05-03-review-modified"),
        )

        for entity_type, kind, identity in combinations:
            with self.subTest(entity_type=entity_type, kind=kind):
                self.assertIn(f">{entity_type}</strong>", content)
                self.assertIn(identity, content)
                self.assertIn(
                    f"gwflow-change-badge gwflow-change-badge--{kind}",
                    content,
                )
        self.assert_announcement(response, "16 semantic changes.")

    def test_review_deltas_render_as_named_rows(self):
        response, _, _, _ = self.render(
            diff_payload=self.load_fixture("semantic_diff.json"),
        )
        content = response.content.decode()

        self.assertIn("<dt>Reviewers</dt>", content)
        self.assertIn("<dt>Passed review</dt>", content)
        self.assertIn("<dt>Completion date</dt>", content)
        self.assertIn("Reviewer One", content)
        self.assertIn("Reviewer Two", content)
        self.assertIn("2026-01-02T00:00:00Z", content)

    def test_gracedb_nullable_numbers_are_not_boolean_coerced(self):
        payload = self.load_fixture("semantic_diff_booleans.json")
        change = payload["changes"][0]

        # This fixture proves that portal booleans are invalid for nullable
        # number fields. Use its exact shape with numeric wire values here so
        # the accepted path can assert that 1 and 0 remain literal numbers.
        change["after"]["has_ns"] = 1
        change["after"]["pipeline_has_mass_gap"] = 0
        change["field_diffs"]["has_ns"]["selected"] = 1
        change["field_diffs"]["pipeline_has_mass_gap"]["selected"] = 0

        response, _, _, _ = self.render(diff_payload=payload)
        region = self.changes_region(response)

        self.assertIn("<dt>Has ns</dt>", region)
        self.assertIn("<dt>Pipeline has mass gap</dt>", region)
        self.assertIn("<dd>Not provided</dd>", region)
        self.assertIn("<dd>1</dd>", region)
        self.assertIn("<dd>0</dd>", region)
        self.assertNotIn("<dd>Yes</dd>", region)
        self.assertNotIn("<dd>No</dd>", region)
        self.assertNotIn("<dd>True</dd>", region)
        self.assertNotIn("<dd>False</dd>", region)
        self.assert_announcement(response, "1 semantic change.")

    def test_null_false_zero_and_empty_string_render_distinctly(self):
        payload = self.semantic_payload(
            changes=[
                {
                    "entity_type": "analysis",
                    "identity": "edge-values",
                    "kind": "modified",
                    "before": {"value": "before"},
                    "after": {"value": "after"},
                    "field_diffs": {
                        "null_value": {"baseline": None, "selected": None},
                        "false_value": {"baseline": False, "selected": False},
                        "zero_value": {"baseline": 0, "selected": 0},
                        "empty_value": {"baseline": "", "selected": ""},
                    },
                }
            ],
        )
        response, _, _, _ = self.render(diff_payload=payload)
        region = self.changes_region(response)

        self.assertIn("<dt>Null value</dt>", region)
        self.assertIn("Not provided", region)
        self.assertIn("<dt>False value</dt>", region)
        self.assertIn("<dd>No</dd>", region)
        self.assertIn("<dt>Zero value</dt>", region)
        self.assertIn("<dd>0</dd>", region)
        self.assertIn("<dt>Empty value</dt>", region)
        self.assertIn("<dd></dd>", region)
        self.assertNotIn(">None<", region)
        self.assertNotIn(">null<", region)
        self.assertNotIn(">false<", region)

    def test_hostile_field_diff_value_is_escaped_not_executed(self):
        hostile = '<script>alert("diff")</script>'
        payload = self.semantic_payload(
            changes=[
                {
                    "entity_type": "analysis",
                    "identity": "hostile",
                    "kind": "modified",
                    "before": {"value": "safe"},
                    "after": {"value": hostile},
                    "field_diffs": {
                        "value": {"baseline": "safe", "selected": hostile},
                    },
                }
            ],
        )
        response, _, _, _ = self.render(diff_payload=payload)
        region = self.changes_region(response)

        self.assertNotIn("<script>", region)
        self.assertIn("&lt;script&gt;alert", region)
        self.assertIn("&quot;diff&quot;", region)
        self.assertIn("&lt;/script&gt;", region)

    def test_settled_statuses_fold_diff_sentence_into_existing_region(self):
        cases = (
            ("semantic", self.semantic_payload(), "live", "1 semantic change."),
            (
                "semantic_empty",
                self.load_fixture("semantic_diff_empty.json"),
                "live",
                "No semantic changes.",
            ),
            ("unavailable", None, "down", "Semantic comparison unavailable."),
            ("failed", None, "failed", "Semantic comparison failed."),
        )
        for name, payload, state, sentence in cases:
            with self.subTest(name=name):
                response, _, _, _ = self.render(
                    diff_payload=payload,
                    diff_state=state,
                )
                self.assert_announcement(response, sentence)

        self.job.current_history_id = self.previous_sha
        self.job.save(update_fields=["current_history_id"])
        response, _, _, _ = self.render(versions=[self.versions[0]])
        self.assert_announcement(
            response,
            "No earlier version available to compare.",
        )

    def test_rendered_output_has_no_json_shim(self):
        response, _, _, _ = self.render(
            diff_payload=self.load_fixture("semantic_diff.json"),
        )
        content = response.content.decode()

        self.assertNotIn("<pre><code>", content)
        self.assertNotIn("Temporary technical inspection aid", content)

    def test_semantic_empty_render_is_distinct(self):
        response, _, get_version, get_diff = self.render(
            diff_payload=self.semantic_payload(changes=[]),
        )

        region = self.changes_region(response)
        self.assertIn(
            "The comparison is valid and contains no semantic changes.",
            region,
        )
        self.assertNotIn("Try again", region)
        self.assertNotIn("None", region)
        get_version.assert_called_once_with(self.sname, 42)
        get_diff.assert_called_once_with(self.sname, 41, 42)

    def test_no_baseline_render_is_distinct_and_skips_diff(self):
        only = [self.versions[0]]
        self.job.current_history_id = self.previous_sha
        self.job.save(update_fields=["current_history_id"])

        response, _, get_version, get_diff = self.render(versions=only)

        region = self.changes_region(response)
        self.assertIn("Changes for selected version 41", region)
        self.assertIn(
            "No earlier version is available to compare against.",
            region,
        )
        self.assertNotIn("Try again", region)
        self.assertNotIn("None", region)
        get_version.assert_called_once_with(self.sname, 41)
        get_diff.assert_not_called()

    def test_unavailable_render_has_exclusive_retry(self):
        with self.assertLogs("bilbyui.views", level="WARNING") as logs:
            response, _, get_version, get_diff = self.render(
                diff_payload=None,
                diff_state="down",
            )

        region = self.changes_region(response)
        self.assertIn(
            "The semantic comparison service is unavailable.",
            region,
        )
        self.assertIn("Try again", region)
        self.assertNotIn("None", region)
        self.assertTrue(any(self.sname in line for line in logs.output))
        get_version.assert_called_once_with(self.sname, 42)
        get_diff.assert_called_once_with(self.sname, 41, 42)

    def test_failed_render_uses_generic_heading_and_no_retry(self):
        secret = "payload-secret-" + ("x" * 200)
        malformed = self.semantic_payload()
        malformed["changes"][0]["field_diffs"] = {secret: {"baseline": 1}}

        with self.assertLogs("bilbyui.views", level="WARNING") as logs:
            response, _, get_version, get_diff = self.render(
                diff_payload=malformed,
            )

        region = self.changes_region(response)
        self.assertIn(">Semantic comparison</h3>", region)
        self.assertIn("The semantic comparison failed.", region)
        self.assertNotIn("Try again", region)
        self.assertNotIn("None", region)
        rendered_logs = "\n".join(logs.output)
        self.assertIn("invalid_field_diff:changes[0]", rendered_logs)
        self.assertNotIn(secret, rendered_logs)
        self.assertNotIn("payload-secret", rendered_logs)
        get_version.assert_called_once_with(self.sname, 42)
        get_diff.assert_called_once_with(self.sname, 41, 42)

    def test_try_again_appears_only_for_unavailable(self):
        cases = (
            ("semantic", self.semantic_payload(), "live", False),
            ("semantic_empty", self.semantic_payload(changes=[]), "live", False),
            ("unavailable", None, "down", True),
            ("failed", None, "failed", False),
        )
        for name, payload, state, expected_retry in cases:
            with self.subTest(name=name):
                response, _, _, _ = self.render(
                    diff_payload=payload,
                    diff_state=state,
                )
                region = self.changes_region(response)
                self.assertEqual("Try again" in region, expected_retry)
                self.assertNotIn("None", region)

    def test_recursion_error_serialising_diff_rows_degrades_gracefully(self):
        with mock.patch("bilbyui.views.json.dumps", side_effect=RecursionError):
            response, _, get_version, get_diff = self.render()

        self.assertEqual(response.status_code, 200)
        region = self.changes_region(response)
        self.assertIn("Not provided", region)
        self.assertNotIn("Try again", region)
        get_version.assert_called_once_with(self.sname, 42)
        get_diff.assert_called_once_with(self.sname, 41, 42)
