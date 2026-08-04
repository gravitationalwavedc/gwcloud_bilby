import unittest

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
                {
                    "uid": "uid-unk-1",
                    "custom_file": {
                        "path": "/data/custom/file.dat",
                        "file_size": 99,
                        "md5_sum": "hash_c",
                    },
                    "weird_field": "invalid_structure_no_crash",
                }
            ]
        }
        files = extract_file_manifest(payload)
        self.assertEqual(len(files), 1)
        self.assertEqual(files[0]["analysis_uid"], "uid-unk-1")
        self.assertEqual(files[0]["path"], "/data/custom/file.dat")

    def test_empty_or_invalid_payload(self):
        self.assertEqual(extract_file_manifest({}), [])
        self.assertEqual(extract_file_manifest(None), [])


if __name__ == "__main__":
    unittest.main()
