import unittest
from unittest.mock import patch

from manifest import extract_file_manifest


class TestManifestExtraction(unittest.TestCase):
    def test_pe_results_and_bayeswave_psd_extraction(self):
        payload = {
            "sname": "S260101a",
            "pe": {
                "results": [
                    {
                        "uid": "uid-pe-1",
                        "config_file": {
                            "path": "/data/pe1/config.ini",
                            "file_size": 1024,
                            "md5_sum": "hash1",
                        },
                        "result_file": {
                            "path": "/data/pe1/result.hdf5",
                            "file_size": 2048,
                            "md5_sum": "hash2",
                        },
                        "pesummary_result_file": None,
                        "bayeswave": {
                            "psd_files": {
                                "H1": {
                                    "path": "/data/pe1/H1_psd.dat",
                                    "file_size": 512,
                                    "md5_sum": "hash3",
                                },
                                "L1": {
                                    "path": "/data/pe1/L1_psd.dat",
                                    "file_size": 512,
                                    "md5_sum": "hash4",
                                },
                            }
                        },
                    }
                ]
            },
        }

        files = extract_file_manifest(payload)
        self.assertEqual(len(files), 4)
        paths = [f["path"] for f in files]
        self.assertIn("/data/pe1/config.ini", paths)
        self.assertIn("/data/pe1/result.hdf5", paths)
        self.assertIn("/data/pe1/H1_psd.dat", paths)
        self.assertIn("/data/pe1/L1_psd.dat", paths)

        # Check fields
        f0 = next(f for f in files if f["path"] == "/data/pe1/config.ini")
        self.assertEqual(f0["analysis_uid"], "uid-pe-1")
        self.assertEqual(f0["file_name"], "config.ini")
        self.assertEqual(f0["file_size"], 1024)
        self.assertEqual(f0["md5_sum"], "hash1")

    def test_bayeswave_psd_as_list(self):
        payload = {
            "pe": {
                "results": [
                    {
                        "uid": "uid-bw-list",
                        "bayeswave": {
                            "psd_files": [
                                {"path": "/data/bw_list1.dat", "file_size": 100},
                                {"path": "/data/bw_list2.dat", "file_size": 200},
                            ]
                        },
                    }
                ]
            }
        }
        files = extract_file_manifest(payload)
        self.assertEqual(len(files), 2)
        self.assertEqual(files[0]["path"], "/data/bw_list1.dat")

    def test_deduplication(self):
        payload = {
            "pe": {
                "results": [
                    {
                        "uid": "uid-dup",
                        "config_file": {"path": "/data/dup.txt", "file_size": 100},
                        "result_file": {"path": "/data/dup.txt", "file_size": 100},
                    }
                ]
            }
        }
        files = extract_file_manifest(payload)
        self.assertEqual(len(files), 1)

    def test_defensive_unknown_section_walking(self):
        payload = {
            "unknown_section": [
                "non_dict_element",
                {"no_uid": 123},
                {
                    "uid": "uid-unk-1",
                    "custom_file": {
                        "path": "/data/custom/file.dat",
                        "file_size": 99,
                        "md5_sum": "hash_c",
                    },
                    "weird_field": "invalid_structure_no_crash",
                },
            ],
            "dict_section": {
                "uid": "uid-dict-1",
                "nested_list": [
                    {"path": "/data/nested/file.dat", "file_size": 50},
                ],
            },
        }
        files = extract_file_manifest(payload)
        self.assertEqual(len(files), 2)
        uids = [f["analysis_uid"] for f in files]
        self.assertIn("uid-unk-1", uids)
        self.assertIn("uid-dict-1", uids)

    def test_missing_path_or_invalid_file_obj(self):
        payload = {
            "pe": {
                "results": [
                    "invalid_result_entry",
                    {
                        "uid": "uid-invalid",
                        "config_file": {"no_path": "foo"},
                        "result_file": "not_a_dict",
                    },
                ]
            }
        }
        files = extract_file_manifest(payload)
        self.assertEqual(files, [])

    def test_section_exception_handling(self):
        payload = {"failing_section": {"uid": "uid-1"}}
        with patch("manifest._build_file_entry", side_effect=Exception("mock error")):
            files = extract_file_manifest(payload)
            self.assertEqual(files, [])

    def test_empty_or_invalid_payload(self):
        self.assertEqual(extract_file_manifest({}), [])
        self.assertEqual(extract_file_manifest(None), [])


if __name__ == "__main__":
    unittest.main()
