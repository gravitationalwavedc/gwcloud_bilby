from unittest import mock

from bilbyui.models import on_bilby_job_label_add_rem
from bilbyui.tests.testcases import BilbyTestCase


class TestOnBilbyJobLabelAddRem(BilbyTestCase):
    def setUp(self):
        self.instance = mock.Mock()

    def test_post_add_calls_elastic_search_update(self):
        on_bilby_job_label_add_rem(
            sender=None,
            instance=self.instance,
            action="post_add",
            pk_set={1},
        )
        self.instance.elastic_search_update.assert_called_once_with()

    def test_post_remove_calls_elastic_search_update(self):
        on_bilby_job_label_add_rem(
            sender=None,
            instance=self.instance,
            action="post_remove",
            pk_set={1},
        )
        self.instance.elastic_search_update.assert_called_once_with()

    def test_other_actions_are_no_op(self):
        for action in ["pre_add", "pre_remove", "post_clear", "pre_clear"]:
            with self.subTest(action=action):
                on_bilby_job_label_add_rem(
                    sender=None,
                    instance=self.instance,
                    action=action,
                    pk_set=set(),
                )
        self.instance.elastic_search_update.assert_not_called()
