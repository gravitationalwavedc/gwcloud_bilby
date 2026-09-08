"""Unit tests for the GWFlow section dispatcher ``_render_gwflow_section``.

These tests exercise the routing/404 branch point in the GWFlow detail
rendering path directly. The three sub-renderers each have their own tests;
here we only assert that the dispatcher forwards the request and sname to the
correct sub-renderer and raises ``Http404`` for an unknown section.
"""

from unittest import mock

from django.http import Http404
from django.test import SimpleTestCase

from bilbyui.views import _render_gwflow_section

REQUEST = mock.Mock()
SNAME = "S230601ag"


class TestRenderGWFlowSection(SimpleTestCase):
    def test_metadata_dispatches_to_metadata_renderer(self):
        with (
            mock.patch("bilbyui.views._render_gwflow_metadata_section", return_value=("content", False)) as metadata,
            mock.patch("bilbyui.views._render_gwflow_files_section") as files,
            mock.patch("bilbyui.views._render_gwflow_history_section") as history,
        ):
            result = _render_gwflow_section(REQUEST, SNAME, "metadata")

        self.assertEqual(result, ("content", False))
        metadata.assert_called_once_with(REQUEST, SNAME)
        files.assert_not_called()
        history.assert_not_called()

    def test_files_dispatches_to_files_renderer(self):
        with (
            mock.patch("bilbyui.views._render_gwflow_files_section", return_value=("content", False)) as files,
            mock.patch("bilbyui.views._render_gwflow_metadata_section") as metadata,
            mock.patch("bilbyui.views._render_gwflow_history_section") as history,
        ):
            result = _render_gwflow_section(REQUEST, SNAME, "files")

        self.assertEqual(result, ("content", False))
        files.assert_called_once_with(REQUEST, SNAME)
        metadata.assert_not_called()
        history.assert_not_called()

    def test_history_dispatches_to_history_renderer(self):
        with (
            mock.patch("bilbyui.views._render_gwflow_history_section", return_value=("content", False)) as history,
            mock.patch("bilbyui.views._render_gwflow_metadata_section") as metadata,
            mock.patch("bilbyui.views._render_gwflow_files_section") as files,
        ):
            result = _render_gwflow_section(REQUEST, SNAME, "history")

        self.assertEqual(result, ("content", False))
        history.assert_called_once_with(REQUEST, SNAME)
        metadata.assert_not_called()
        files.assert_not_called()

    def test_unknown_section_raises_http404(self):
        with (
            mock.patch("bilbyui.views._render_gwflow_metadata_section") as metadata,
            mock.patch("bilbyui.views._render_gwflow_files_section") as files,
            mock.patch("bilbyui.views._render_gwflow_history_section") as history,
        ):
            with self.assertRaises(Http404):
                _render_gwflow_section(REQUEST, SNAME, "bogus")

        metadata.assert_not_called()
        files.assert_not_called()
        history.assert_not_called()
