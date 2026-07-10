from bilbyui.models import BilbyJob, Label
from bilbyui.tests.test_utils import create_test_ini_string
from bilbyui.tests.testcases import BilbyTestCase
from bilbyui.views import _available_labels_for_job


class TestAvailableLabelsForJob(BilbyTestCase):
    @classmethod
    def setUpTestData(cls):
        cls.ini = create_test_ini_string({"detectors": "['H1']"})
        cls.assigned_label = Label.objects.create(
            name="GardenerAssigned",
            description="Already on the job",
            protected=False,
        )
        cls.available_label = Label.objects.create(
            name="GardenerAvailable",
            description="Should appear in results",
            protected=False,
        )
        cls.protected_label = Label.objects.create(
            name="GardenerProtected",
            description="Protected label",
            protected=True,
        )

    def setUp(self):
        self.authenticate()
        self.job = BilbyJob.objects.create(
            user_id=self.user.id,
            name="labels_job",
            description="Job for label helper tests",
            private=False,
            ini_string=self.ini,
        )

    def test_excludes_assigned_and_protected_labels(self):
        self.job.labels.add(self.assigned_label)

        available = list(_available_labels_for_job(self.job).order_by("name"))

        available_names = {label.name for label in available}
        self.assertIn(self.available_label.name, available_names)
        self.assertNotIn(self.assigned_label.name, available_names)
        self.assertNotIn(self.protected_label.name, available_names)

    def test_returns_all_non_protected_labels_when_job_has_none(self):
        available = list(_available_labels_for_job(self.job).order_by("name"))

        available_names = {label.name for label in available}
        self.assertIn(self.available_label.name, available_names)
        self.assertIn(self.assigned_label.name, available_names)
        self.assertNotIn(self.protected_label.name, available_names)
