# Migration from the Current Repository Layout

## Current issue

The repository currently has related files split across:
- `config-schema/`
- `compute-policy-v0.2/`

Each contains some mix of schemas, examples, docs, and validation scripts.

## Recommended target

```text
chia-experiment-contracts-v0.2/
├── ai-tutor-config/
├── attention-experiments/
├── compute-policy/
├── run-record/
├── docs/
└── scripts/
```

## Suggested Git strategy

Create a new branch from the current config-schema work:

```bash
git switch feat/config-schema
git pull --ff-only origin feat/config-schema
git switch -c feat/experiment-contracts-v0.2
```

Copy this folder into the repository root, validate it, stage only this folder, commit, and push:

```bash
git add chia-experiment-contracts-v0.2/
git commit -m "Add clean v0.2 experiment contracts architecture"
git push -u origin feat/experiment-contracts-v0.2
```

Do not delete the old folders in the same first commit unless the team explicitly agrees to the migration. A safer review is:
1. add the new clean structure,
2. validate and review,
3. remove/deprecate the old structure in a follow-up commit.
