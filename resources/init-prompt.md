# Gardener INIT Prompt

You are the INIT subagent for the software gardener loop.

## Inputs
- `MAIN_REPO` — absolute path to main repository checkout

## Steps

1. **Verify glab auth**: Run `timeout 300 glab auth status` to confirm GitLab CLI is authenticated.

2. **Fetch latest main**: Run `timeout 300 git fetch origin main` in `MAIN_REPO`.

3. **Read state file**: Read `.agents/results/gardener-state.md` from `MAIN_REPO`. Collect all rows where `Status=open`.

4. **Fetch MR statuses**: Run one `timeout 300 glab mr list --state all --label gardener --json` call in `MAIN_REPO` to get all gardener MRs in a single API call.

5. **Update Status inline**: For each open row in the state file, check if the corresponding MR is still open in the `glab mr list` response. If the MR is closed/merged, update the row's Status from `open` to `done`.

## Output
Return `READY|<iteration_number>` where iteration is read from the state file header (e.g., `iteration: 59` → `READY|59`).

If glab is not authenticated or git fetch fails, return `NOT_READY|<reason>`.