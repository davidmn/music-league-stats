# Git hooks

## Pre-commit

The pre-commit hook runs the test suite and `python3 generate.py`. The commit is aborted if either fails.

### Install

From the project root:

```bash
cp hooks/pre-commit .git/hooks/pre-commit && chmod +x .git/hooks/pre-commit
```

Or, to install from anywhere:

```bash
cp "$(git rev-parse --show-toplevel)/hooks/pre-commit" "$(git rev-parse --show-toplevel)/.git/hooks/pre-commit"
chmod +x "$(git rev-parse --show-toplevel)/.git/hooks/pre-commit"
```
