# htmx migration — GitLab issues reference

Created on 2026-06-18.

## Epic

- **#3** — Migrate gwcloud_bilby frontend from React/Relay to htmx + Django templates
  https://gitlab.com/groups/CAS-eResearch/GWDC/-/epics/3

## Issues

| # | Title | URL |
|---|---|---|
| 2 | Bootstrap htmx + Alpine + base template | https://gitlab.com/CAS-eResearch/GWDC/gwcloud_bilby/-/work_items/2 |
| 3 | Service layer extraction | https://gitlab.com/CAS-eResearch/GWDC/gwcloud_bilby/-/work_items/3 |
| 4 | Public jobs list page | https://gitlab.com/CAS-eResearch/GWDC/gwcloud_bilby/-/work_items/4 |
| 5 | My jobs list page | https://gitlab.com/CAS-eResearch/GWDC/gwcloud_bilby/-/work_items/5 |
| 6 | View job page (read-only) | https://gitlab.com/CAS-eResearch/GWDC/gwcloud_bilby/-/work_items/6 |
| 7 | Inline edit: name + description | https://gitlab.com/CAS-eResearch/GWDC/gwcloud_bilby/-/work_items/7 |
| 8 | Inline edit: privacy | https://gitlab.com/CAS-eResearch/GWDC/gwcloud_bilby/-/work_items/8 |
| 9 | Inline edit: labels | https://gitlab.com/CAS-eResearch/GWDC/gwcloud_bilby/-/work_items/9 |
| 10 | Inline edit: event ID + typeahead | https://gitlab.com/CAS-eResearch/GWDC/gwcloud_bilby/-/work_items/10 |
| 11 | API tokens page | https://gitlab.com/CAS-eResearch/GWDC/gwcloud_bilby/-/work_items/11 |
| 12 | URL swap + htmx 404 | https://gitlab.com/CAS-eResearch/GWDC/gwcloud_bilby/-/work_items/12 |
| 13 | Delete React app + Node tooling | https://gitlab.com/CAS-eResearch/GWDC/gwcloud_bilby/-/work_items/13 |
| 15 | Navbar parity with React Menu | https://gitlab.com/CAS-eResearch/GWDC/gwcloud_bilby/-/work_items/15 |
| 16 | Event ID column on job list pages | https://gitlab.com/CAS-eResearch/GWDC/gwcloud_bilby/-/work_items/16 |
| 17 | Fix My Jobs link on public jobs page | https://gitlab.com/CAS-eResearch/GWDC/gwcloud_bilby/-/work_items/17 |
| 18 | Legacy React URL redirects | https://gitlab.com/CAS-eResearch/GWDC/gwcloud_bilby/-/work_items/18 |
| 19 | Restore Google Analytics page tracking | https://gitlab.com/CAS-eResearch/GWDC/gwcloud_bilby/-/work_items/19 |

## Dependency graph (from issue bodies)

```
2 (bootstrap)
 └─ 3 (services)
     ├─ 4 (public jobs)          ─┐
     ├─ 5 (my jobs)              ─┤
     ├─ 6 (view job)             ─┤
     │   ├─ 7 (edit name+desc)  ─┤
     │   ├─ 8 (privacy)         ─┤
     │   ├─ 9 (labels)          ─┤
     │   └─ 10 (event id)       ─┤
     └─ 11 (api tokens)          ─┤
                                  └─ 12 (URL swap + 404)
                                      └─ 13 (delete React)
                                          ├─ 15 (navbar parity)
                                          ├─ 16 (event ID column)
                                          ├─ 17 (My Jobs link fix)
                                          ├─ 18 (legacy URL redirects)
                                          └─ 19 (Google Analytics)
```

Issues #15–#19 are **React parity** follow-ups after the migration lands. They
restore UX the htmx frontend should match from the old React app. **New job** and
**duplicate job** submission are intentionally out of scope across all five.

Suggested implementation order for #15–#19: **17 → 18 → 15 → 16 → 19**.

## Notes

- Pre-existing issue #1 (Update ozstar job submission) is unrelated and was not modified.
- A test issue #14 was created and immediately closed during setup.
- All cross-references in the issue bodies use real GitLab issue numbers (not placeholders).
- Issues #2–#13 and #15–#19 are linked to epic #3 via the `issueSetEpic` GraphQL mutation.
