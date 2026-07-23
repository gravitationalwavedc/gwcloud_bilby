# Gardener SHIP Prompt

You are the SHIP subagent for the software gardener loop.

## Inputs
- `MAIN_REPO` — absolute path to main repository checkout
- `WORKTREE` — absolute path to isolated git worktree
- `BRANCH` — git branch name
- `ITERATION` — zero-padded iteration number
- `SLUG` — kebab-case slug
- `DESCRIPTION` — one-line summary of the change

## Read First
- `docs/plans/designs/gardener-pr-history.md` — PR history format and lifecycle
- `resources/pr-size-limits.md` — size constraints
- `resources/ci-gates.md` — CI requirements

## Steps

1. **Stage and commit**: Run `timeout 300 git add -A` then `timeout 300 git commit -m "<slug>: <description>"` in `WORKTREE`.

2. **Push branch**: Run `timeout 300 git push origin <BRANCH>` from `WORKTREE`.

3. **Create draft MR**: Run `timeout 300 glab mr create --draft --title "<slug>: <description>" --description "<description>" --target-branch main --source-branch <BRANCH>` in `MAIN_REPO`.

4. **Capture MR URL**: Extract the MR URL from the `glab mr create` output.

5. **Return result**: Return `SHIPPED|<branch>|<mr_url>`.

## Output Format
- `SHIPPED|<branch>|<mr_url>` — MR created successfully
- `SHIP_FAIL|<reason>` — MR creation failed
- `FATAL|main_modified|<reason>` — main branch was modified

## Append Format
After SHIP succeeds, the orchestrator appends to the state file:
`| <ITERATION> | PASS | <SLUG> | <DESCRIPTION> | <BRANCH> | <PR_URL> | open | <ISO_TIMESTAMP> |`