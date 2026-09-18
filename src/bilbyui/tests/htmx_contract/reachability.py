"""Declarative reachability inventory for issue #60 HTMX contracts.

Values are grounded in production templates and views.  A
BLOCKING_PRODUCT_GAP value means issue #60 requires the state but production
has no corresponding branch; downstream tests must not fabricate that state.
"""

REACHABLE = "reachable"


def not_applicable(reason):
    """Keep declarations concise while returning plain strings only."""
    return f"not_applicable({reason})"


CONTRACTS = {
    # gwflow_jobs.html:20-21 exposes loading; _gwflow_job_list_fragment.html:1-40
    # exposes content, empty, error and retry; views.py:1483-1537 builds responses.
    "gwflow_list_search_filter_pagination": {
        "family": "gwflow list/search/filter/pagination",
        "method": "GET",
        "url_name": "bilbyui:gwflow_jobs",
        "target": "#gwflow-job-list",
        "swap": "innerHTML",
        "states": {
            "idle": REACHABLE,
            "loading": REACHABLE,
            "content": REACHABLE,
            "empty": REACHABLE,
            "stale": REACHABLE,
            "error": REACHABLE,
            "retry": REACHABLE,
        },
        "evidence": [
            "src/bilbyui/templates/bilbyui/gwflow_jobs.html:20-21",
            "src/bilbyui/templates/bilbyui/_gwflow_job_list_fragment.html:1-40",
            "src/bilbyui/templates/bilbyui/_search_state_sync.html:13-17",
            "src/bilbyui/views.py:1483-1537",
        ],
    },
    # gwflow_detail.html:30-73 defines navigation, target, swap and skeleton.
    # views.py:1547-1555 returns an HTMX section fragment.
    "gwflow_detail_metadata": {
        "family": "detail metadata/files/history",
        "method": "GET",
        "url_name": "bilbyui:gwflow_job_metadata",
        "target": "#detail-pane",
        "swap": "innerHTML",
        "states": {
            "idle": REACHABLE,
            "loading": REACHABLE,
            "content": REACHABLE,
            "empty": REACHABLE,
            "stale": REACHABLE,
            "error": REACHABLE,
            "retry": REACHABLE,
        },
        "evidence": [
            "src/bilbyui/templates/bilbyui/gwflow_detail.html:30-35,73",
            "src/bilbyui/templates/bilbyui/_gwflow_metadata.html:26,38",
            "src/bilbyui/views.py:1547-1555,1662-1697",
            "src/bilbyui/views.py:1667-1680 (down error and retry branch)",
        ],
    },
    "gwflow_detail_files": {
        "family": "detail metadata/files/history",
        "method": "GET",
        "url_name": "bilbyui:gwflow_job_files",
        "target": "#detail-pane",
        "swap": "innerHTML",
        "states": {
            "idle": REACHABLE,
            "loading": REACHABLE,
            "content": REACHABLE,
            "empty": REACHABLE,
            "stale": not_applicable("files section has no stale semantic"),
            "error": not_applicable(
                "files render from the local mirror; portal outage only degrades analysis enrichment and never blocks the region"
            ),
            "retry": not_applicable("files render from the local mirror; no blocking portal error exists to retry"),
        },
        "evidence": [
            "src/bilbyui/templates/bilbyui/gwflow_detail.html:44-49,73",
            "src/bilbyui/templates/bilbyui/_gwflow_files.html:1-89",
            "src/bilbyui/views.py:1547-1555,1633-1659 (local-first rendering; portal state only controls analysis enrichment)",
        ],
    },
    "gwflow_detail_history": {
        "family": "detail metadata/files/history",
        "method": "GET",
        "url_name": "bilbyui:gwflow_job_history",
        "target": "#detail-pane",
        "swap": "innerHTML",
        "states": {
            "idle": REACHABLE,
            "loading": REACHABLE,
            "content": REACHABLE,
            "empty": REACHABLE,
            "stale": REACHABLE,
            "error": REACHABLE,
            "retry": REACHABLE,
        },
        "evidence": [
            "src/bilbyui/templates/bilbyui/gwflow_detail.html:57-73",
            "src/bilbyui/templates/bilbyui/_gwflow_history_version.html:2-23",
            "src/bilbyui/views.py:1700-1792",
            "src/bilbyui/views.py:1704-1719 (down error and retry branch)",
        ],
    },
    # Version links and comparison form use the same outer region.
    "gwflow_version_select_compare": {
        "family": "version select+compare",
        "method": "GET",
        "url_name": "bilbyui:gwflow_job_history",
        "target": "#gwflow-history-region",
        "swap": "outerHTML",
        "states": {
            "idle": REACHABLE,
            "loading": REACHABLE,
            "content": REACHABLE,
            "empty": REACHABLE,
            "stale": REACHABLE,
            "error": REACHABLE,
            "retry": REACHABLE,
        },
        "evidence": [
            "src/bilbyui/templates/bilbyui/_gwflow_history_version_list.html:17-27",
            "src/bilbyui/templates/bilbyui/_gwflow_history_version.html:29-65",
            "src/bilbyui/views.py:1700-1828",
        ],
    },
    # Modal loads via event_id_modal; search results replace their own result box.
    "event_id_modal_open": {
        "family": "event-ID search modal",
        "method": "GET",
        "url_name": "bilbyui:event_id_modal",
        "target": "#modal-container",
        "swap": "innerHTML",
        "states": {
            "idle": REACHABLE,
            "loading": REACHABLE,
            "content": REACHABLE,
            "empty": not_applicable("modal shell is always rendered"),
            "stale": not_applicable("modal open has no stale semantic"),
            "error": REACHABLE,
            "retry": REACHABLE,
        },
        "evidence": [
            "src/bilbyui/views.py:2271-2273",
            "src/bilbyui/templates/bilbyui/_job_field_event_id.html:13-35",
            "src/bilbyui/templates/bilbyui/_event_id_modal_error.html:1-3",
            "src/bilbyui/views.py:2285-2301",
        ],
    },
    "event_id_search": {
        "family": "event-ID search modal",
        "method": "GET",
        "url_name": "bilbyui:event_id_search",
        "target": "#event-id-results",
        "swap": "innerHTML",
        "states": {
            "idle": REACHABLE,
            "loading": REACHABLE,
            "content": REACHABLE,
            "empty": REACHABLE,
            "stale": not_applicable("search uses current query response only"),
            "error": REACHABLE,
            "retry": REACHABLE,
        },
        "evidence": [
            "src/bilbyui/views.py:2243-2266",
            "src/bilbyui/templates/bilbyui/_event_id_modal.html:11-26",
            "src/bilbyui/templates/bilbyui/_event_id_search_error.html:1-2",
        ],
    },
    # Text, privacy, labels and event ID use equivalent field-level replacement.
    "job_field_edits": {
        "family": "job field edits",
        "method": "GET/POST",
        "url_name": (
            "bilbyui:view_job_field_partial; bilbyui:edit_job_name; "
            "bilbyui:edit_job_description; bilbyui:edit_job_privacy; "
            "bilbyui:edit_job_labels; bilbyui:edit_job_event_id"
        ),
        "target": "#field-<field>-<job_id> / #event-id-field-<job_id>",
        "swap": "outerHTML",
        "states": {
            "idle": REACHABLE,
            "loading": REACHABLE,
            "content": REACHABLE,
            "empty": REACHABLE,
            "stale": not_applicable("field edit has no stale response semantic"),
            "error": REACHABLE,
            "retry": REACHABLE,
        },
        "evidence": [
            "src/bilbyui/templates/bilbyui/_job_field_text.html:5-57,71-85",
            "src/bilbyui/templates/bilbyui/_event_id_result.html:2-4",
            "src/bilbyui/views.py:2101-2306",
            "src/bilbyui/templates/bilbyui/_job_field_text.html:3-96",
            "src/bilbyui/templates/bilbyui/_job_field_labels.html:3-42",
            "src/bilbyui/templates/bilbyui/_job_field_privacy.html:3-24",
        ],
    },
    "token_create": {
        "family": "token create/revoke/copy",
        "method": "POST",
        "url_name": "bilbyui:api_token_create",
        "target": "#token-actions",
        "swap": "innerHTML",
        "states": {
            "idle": REACHABLE,
            "loading": REACHABLE,
            "content": REACHABLE,
            "empty": REACHABLE,
            "stale": not_applicable("token creation has no stale semantic"),
            "error": REACHABLE,
            "retry": REACHABLE,
        },
        "evidence": [
            "src/bilbyui/templates/bilbyui/api_token.html:15-29",
            "src/bilbyui/templates/bilbyui/_token_create_success.html:1-19",
            "src/bilbyui/views.py:2377-2428",
            "src/bilbyui/templates/bilbyui/_token_actions.html:8-35",
            "src/bilbyui/templates/bilbyui/_token_create_error.html:1-3",
        ],
    },
    "token_revoke": {
        "family": "token create/revoke/copy",
        "method": "DELETE",
        "url_name": "bilbyui:api_token_revoke",
        "target": "closest [data-token-id] (event-driven removal)",
        "swap": "none (204 + HX-Trigger token-revoked)",
        "states": {
            "idle": REACHABLE,
            "loading": REACHABLE,
            "content": REACHABLE,
            "empty": REACHABLE,
            "stale": not_applicable("revocation has no stale response semantic"),
            "error": REACHABLE,
            "retry": REACHABLE,
        },
        "evidence": [
            "src/bilbyui/templates/bilbyui/api_token.html:75-135",
            "src/bilbyui/views.py:2432-2450",
            "src/bilbyui/templates/bilbyui/_token_row.html:27-48",
            "src/bilbyui/templates/bilbyui/_token_revoke_error.html:1-5",
        ],
    },
    "token_copy": {
        "family": "token create/revoke/copy",
        "method": "client-side clipboard",
        "url_name": not_applicable("copy does not call a Django endpoint"),
        "target": ".token-copy-status",
        "swap": "textContent",
        "states": {
            "idle": REACHABLE,
            "loading": not_applicable("clipboard operation has no HTMX request lifecycle"),
            "content": REACHABLE,
            "empty": not_applicable("copy button exists only with a newly created token"),
            "stale": not_applicable("clipboard operation has no stale response"),
            "error": REACHABLE,
            "retry": REACHABLE,
        },
        "evidence": [
            "src/bilbyui/templates/bilbyui/api_token.html:55-72",
            "src/bilbyui/templates/bilbyui/_token_create_success.html:2-11",
        ],
    },
}
