import uuid
from unittest import mock

from django.test import override_settings
from graphql import GraphQLResolveInfo

from bilbyui.models import AnonymousMetrics
from bilbyui.tests.testcases import BilbyTestCase
from bilbyui.utils.anonymous_metrics import AnonymousMetricsMiddleware


@override_settings(IGNORE_ELASTIC_SEARCH=True)
class TestAnonymousMetricsMiddlewareResolve(BilbyTestCase):
    def _make_info(self, header, authenticated=False, nested=False):
        user = mock.Mock()
        user.is_authenticated = authenticated
        path = mock.Mock()
        path.prev = mock.Mock() if nested else None
        path.key = "bilbyJob"
        context = mock.Mock()
        context.user = user
        context.headers = {}
        if header is not None:
            context.headers["X-Correlation-Id"] = header
        info = mock.Mock(spec=GraphQLResolveInfo)
        info.context = context
        info.path = path
        return info

    def _make_next(self):
        return mock.Mock(return_value="next-result")

    def test_resolve_no_header(self):
        info = self._make_info(None)
        next_mw = self._make_next()
        self.assertEqual(AnonymousMetricsMiddleware().resolve(next_mw, None, info), "next-result")
        next_mw.assert_called_once()

    def test_resolve_authenticated_user(self):
        info = self._make_info(str(uuid.uuid4()) + " " + str(uuid.uuid4()), authenticated=True)
        next_mw = self._make_next()
        self.assertEqual(AnonymousMetricsMiddleware().resolve(next_mw, None, info), "next-result")
        next_mw.assert_called_once()

    def test_resolve_nested_path(self):
        info = self._make_info(str(uuid.uuid4()) + " " + str(uuid.uuid4()), nested=True)
        next_mw = self._make_next()
        self.assertEqual(AnonymousMetricsMiddleware().resolve(next_mw, None, info), "next-result")
        next_mw.assert_called_once()

    def test_resolve_no_space(self):
        info = self._make_info(uuid.uuid4().hex)
        next_mw = self._make_next()
        self.assertEqual(AnonymousMetricsMiddleware().resolve(next_mw, None, info), "next-result")
        next_mw.assert_called_once()

    def test_resolve_wrong_id_count(self):
        info = self._make_info("a b c")
        next_mw = self._make_next()
        self.assertEqual(AnonymousMetricsMiddleware().resolve(next_mw, None, info), "next-result")
        next_mw.assert_called_once()

    def test_resolve_invalid_uuid(self):
        info = self._make_info("not-a-uuid not-a-uuid-either")
        next_mw = self._make_next()
        self.assertEqual(AnonymousMetricsMiddleware().resolve(next_mw, None, info), "next-result")
        next_mw.assert_called_once()

    def test_resolve_valid_create(self):
        pid = uuid.uuid4()
        sid = uuid.uuid4()
        info = self._make_info(str(pid) + " " + str(sid))
        next_mw = self._make_next()
        self.assertEqual(AnonymousMetricsMiddleware().resolve(next_mw, None, info, foo="bar"), "next-result")
        next_mw.assert_called_once()

        entry = AnonymousMetrics.objects.get(public_id=pid, session_id=sid)
        self.assertEqual(entry.request, "bilbyJob")
        self.assertEqual(entry.params, '{"foo": "bar"}')
