from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from graphql import GraphQLError

from bilbyui.tests.testcases import BilbyTestCase
from bilbyui.views import create_bilby_job_from_ini_string


def _make_params(name="TestJob", private=False, cluster="default", ini_string="[a]\nb=1"):
    return SimpleNamespace(
        ini_string=SimpleNamespace(ini_string=ini_string),
        details=SimpleNamespace(name=name, description="desc", private=private, cluster=cluster),
    )


def _make_args():
    return SimpleNamespace(
        outdir=".",
        label="TestJob",
        prior_file=None,
        gps_file=None,
        timeslide_file=None,
        injection_file=None,
        psd_dict=None,
    )


class TestCreateBilbyJobFromIniString(BilbyTestCase):
    def test_missing_ini_string_raises_error(self):
        params = _make_params(ini_string=None)

        with self.assertRaisesRegex(GraphQLError, "A valid ini string must be provided."):
            create_bilby_job_from_ini_string(MagicMock(), params)

    @patch("bilbyui.views._parse_embargo_args", return_value=(1.0, False))
    @patch("bilbyui.views.should_embargo_job", return_value=True)
    def test_embargo_rejection_raises_error(self, mock_should_embargo, mock_parse_embargo):
        params = _make_params()

        with self.assertRaisesRegex(GraphQLError, "Only LIGO users may run real jobs on embargoed LIGO data"):
            create_bilby_job_from_ini_string(MagicMock(), params)

        mock_parse_embargo.assert_called_once()
        mock_should_embargo.assert_called_once()

    def _patch_successful_creation(self, has_supporting_files):
        bilby_job = MagicMock()
        bilby_job.has_supporting_files.return_value = has_supporting_files
        return [
            patch("bilbyui.views.BilbyJob", return_value=bilby_job),
            patch("bilbyui.views.SupportingFile"),
            patch("bilbyui.views.bilby_args_to_ini_string", return_value="ini"),
            patch("bilbyui.views.parse_supporting_files", return_value={}),
            patch("bilbyui.views.bilby_ini_args_to_data_input", return_value=MagicMock()),
            patch("bilbyui.views._capture_supporting_files", return_value=(None, None, None, None, None)),
            patch("bilbyui.views._get_default_prior_files", return_value=frozenset()),
            patch("bilbyui.views.should_embargo_job", return_value=False),
            patch("bilbyui.views._parse_embargo_args", return_value=(None, False)),
            patch("bilbyui.views.bilby_ini_string_to_args", return_value=_make_args()),
        ]

    def test_successful_creation_without_supporting_files_submits(self):
        user = MagicMock()
        params = _make_params()
        patches = self._patch_successful_creation(has_supporting_files=False)

        with (
            patches[0] as mock_bilby_job_cls,
            patches[1] as mock_supporting_file,
            patches[2] as mock_to_ini,
            patches[3] as mock_parse_sf,
            patches[4],
            patches[5],
            patches[6],
            patches[7] as mock_should_embargo,
            patches[8] as mock_parse_embargo,
            patches[9] as mock_to_args,
        ):
            bilby_job, supporting_file_details = create_bilby_job_from_ini_string(user, params)

        mock_to_args.assert_called_once()
        mock_parse_embargo.assert_called_once()
        self.assertEqual(mock_should_embargo.call_count, 2)
        mock_to_ini.assert_called_once()
        mock_parse_sf.assert_called_once()

        mock_bilby_job_cls.assert_called_once_with(
            user=user,
            name="TestJob",
            description="desc",
            private=False,
            ini_string="ini",
            is_ligo_job=False,
            cluster="default",
        )
        mock_supporting_file.save_from_parsed.assert_called_once_with(bilby_job, {})
        bilby_job.save.assert_called_once()
        bilby_job.submit.assert_called_once()
        self.assertEqual(supporting_file_details, mock_supporting_file.save_from_parsed.return_value)

    def test_successful_creation_with_supporting_files_does_not_submit(self):
        user = MagicMock()
        params = _make_params()
        patches = self._patch_successful_creation(has_supporting_files=True)

        with (
            patches[0],
            patches[1],
            patches[2],
            patches[3],
            patches[4],
            patches[5],
            patches[6],
            patches[7],
            patches[8],
            patches[9],
        ):
            bilby_job, _ = create_bilby_job_from_ini_string(user, params)

        bilby_job.save.assert_called_once()
        bilby_job.submit.assert_not_called()
