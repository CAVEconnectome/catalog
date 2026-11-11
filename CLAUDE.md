# CLAUDE.md

## Releasing a new version

Every new version needs two things, and they must stay in sync:

1. **A `v{version}` git tag pushed to this repo.** Cloud Build triggers on the tag
   (`cloudbuild.yaml`) and pushes the image `caveconnectome/cave-catalog:v{version}`.
2. **`charts/catalog/Chart.yaml` in `CAVEconnectome/cave-helm-charts` updated** so that
   `appVersion` is the new version and the chart `version` is the same number. The chart
   deploys the image tag `v{appVersion}`, so a chart that isn't updated keeps deploying the
   old image.

The app and the chart share one version number. The chart can also be bumped on its own
(for a template change), so the new version must be past both: bump from whichever of the
app version (`pyproject.toml`) and the chart `version` is higher. For example, app `0.1.0`
and chart `0.1.3` give a patch release of `0.1.4`, and the app skips `0.1.1`–`0.1.3`.

### How to do it

Run the **publish release** GitHub Actions workflow (`.github/workflows/release.yml`) and
pick `major`, `minor` or `patch`. It does all of the above: picks the higher base version,
bumps `pyproject.toml` with `bump-my-version` (which also relocks `uv.lock` in the same
commit), pushes the commit and tag, creates the GitHub Release, and commits the new
`version` and `appVersion` to `cave-helm-charts`. Use `dry-run` to check the version first.

Don't bump the version, tag, or edit `Chart.yaml` by hand. Doing only part of it leaves the
tag, image and chart out of sync.
