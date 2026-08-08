import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger("gwflow_ingest.manifest")


def _build_file_entry(analysis_uid: str, file_obj: dict | None) -> dict | None:
    if not isinstance(file_obj, dict):
        return None
    path = file_obj.get("path")
    if not path:
        return None

    file_name = Path(path).name
    file_size = file_obj.get("file_size")
    md5_sum = file_obj.get("md5_sum", "")

    return {
        "analysis_uid": analysis_uid,
        "path": path,
        "file_name": file_name,
        "file_size": file_size,
        "md5_sum": md5_sum,
    }


def extract_file_manifest(detail: dict) -> list[dict]:
    """Walk the portal detail payload -> [{analysis_uid, path, file_name, file_size, md5_sum}].

    Sources:
      - pe.results[]: config_file, result_file, pesummary_result_file (analysis_uid = result['uid'])
      - pe.results[].bayeswave: per-detector PSD file entries (same uid)
      - any other section item with a 'uid' and a file-like nested object ({path, md5_sum, ...})
        - walk sections defensively; unknown shapes are skipped with a debug log, never raise.
      - file_name = basename(path); file_size/md5_sum = nested object fields when present.

    Deduplicate on (analysis_uid, path).
    """
    if not isinstance(detail, dict):
        return []

    manifest: list[dict] = []
    seen: set[tuple[str, str]] = set()

    def add_file(analysis_uid: str, file_obj: Any):
        entry = _build_file_entry(analysis_uid, file_obj)
        if entry:
            key = (entry["analysis_uid"], entry["path"])
            if key not in seen:
                seen.add(key)
                manifest.append(entry)

    # 1. Standard PE results processing
    pe_section = detail.get("pe")
    if isinstance(pe_section, dict):
        results = pe_section.get("results")
        if isinstance(results, list):
            for res in results:
                if not isinstance(res, dict):
                    continue
                uid = res.get("uid", "")
                add_file(uid, res.get("config_file"))
                add_file(uid, res.get("result_file"))
                add_file(uid, res.get("pesummary_result_file"))

                # BayesWave detector PSD files
                bayeswave = res.get("bayeswave")
                if isinstance(bayeswave, dict):
                    psd_files = bayeswave.get("psd_files")
                    if isinstance(psd_files, dict):
                        for psd_obj in psd_files.values():
                            add_file(uid, psd_obj)
                    elif isinstance(psd_files, list):
                        for psd_obj in psd_files:
                            add_file(uid, psd_obj)

    # 2. Defensive generic section walking
    for section_key, section_val in detail.items():
        if section_key in ("pe", "raw_payload", "libraries"):
            continue
        try:
            items_to_check = []
            if isinstance(section_val, list):
                items_to_check = section_val
            elif isinstance(section_val, dict):
                items_to_check = [section_val]

            for item in items_to_check:
                if not isinstance(item, dict):
                    continue
                item_uid = item.get("uid", "")
                if not item_uid:
                    continue

                for field_key, field_val in item.items():
                    if field_key == "uid":
                        continue
                    if isinstance(field_val, dict) and "path" in field_val:
                        add_file(item_uid, field_val)
                    elif isinstance(field_val, list):
                        for elem in field_val:
                            if isinstance(elem, dict) and "path" in elem:
                                add_file(item_uid, elem)
        except Exception as e:
            logger.debug("Skipping section %s due to unexpected structure: %s", section_key, e)

    return manifest
