# Git hooks for urpx-rate-plans

Versioned pre-commit hook(s) that keep derived artifacts (reports/, etc.) in sync with tariff filings.

## One-time install

```bash
git config core.hooksPath dev/git-hooks
```

That points git at this directory for hook execution. The setting is per-checkout — each contributor runs it once. Run from any directory inside the repo.

To uninstall:

```bash
git config --unset core.hooksPath
```

## Hooks

### `pre-commit`

Triggers when any `us/**/*.toml`, `us/**/*.jsonld`, or any generator in `dev/` is staged. Re-runs the generators (the list lives in `dev/check_all.py`, so the hook does not keep its own) and stages any resulting `reports/` changes into the same commit, then runs `dev/gate.sh --fast`.

**The hook blocks.** A gate failure aborts the commit with the gate's own exit code (1 regression, 2 drift, 3 refused). There is no CI in this repository, so the hook is the only automatic check.

Set `URPXT_SKIP_REPORTS=1` to skip only the regeneration and staging while still running the gate, for commits meant to be read as data. `--no-verify` disarms everything and is the deliberate escape hatch. Docs-only commits (`README.md`, `LAYOUT.md`, `dev/git-hooks/*`, etc.) skip the hook and aren't slowed down.

The generators need the packages in `dev/requirements.txt`. If `URPX_RATE_PLANS_VENV` names a virtualenv, the hook activates it; otherwise `python3` on `PATH` must already have them.

If a generator fails, the commit is aborted with a non-zero exit. Re-stage / fix and retry, or pass `git commit --no-verify` to bypass intentionally (e.g. for a revert that needs to desync reports).
