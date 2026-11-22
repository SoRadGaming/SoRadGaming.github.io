# SoRadGaming Apps: Feather source

**Add this in Feather (Sources → +):**

```
https://soradgaming.github.io/source.json
```

It lists every app in [`apps.json`](apps.json). Each app's own CI publishes its IPA and an `app.json` entry to
`https://soradgaming.github.io/<repo>/`. This repo's workflow then gathers them into one `source.json` and a
landing page, and deploys it to GitHub Pages.

The workflow runs on push, every 30 minutes, on demand, and when an app's CI sends a `repository_dispatch`
(`app-updated`). If an app can't be fetched, its last published entry is kept.

## Adding a new app

1. In the app's repo, have CI deploy `<IPA>`, `icon.png` and `app.json` to its GitHub Pages site. Use
   `TR256i_Thermal/Config/feather_manifest.py` and its `ios.yml` as the template.
2. Add `{ "repo": "<RepoName>" }` to `apps.json` and push.
3. Optional, for instant updates: create a fine-grained token with **Contents: read & write** on this repo only.
   Save it as the `FEATHER_SOURCE_TOKEN` secret in the app repo.
