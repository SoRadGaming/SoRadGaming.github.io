#!/usr/bin/env python3
"""Builds the shared Feather / AltStore source from every app listed in apps.json.

Each app repo publishes its own entry on GitHub Pages:
    https://<owner>.github.io/<repo>/app.json     (preferred)
    https://<owner>.github.io/<repo>/source.json  (fallback: first app in that source)
If an app can't be fetched right now, its entry from the currently live shared source is kept, so a hiccup in one
repo never drops an app from Feather.

Mirroring (MIRROR=1, set in CI): each app's IPA is copied into a GitHub Release of THIS repo
(tag <repo>-<version>) and the source points at that release asset. Those URLs never disappear, unlike the app's
Pages site which only holds its latest IPA, so a Feather copy of the source that is a few builds old still
installs, and older versions stay installable from the version history.

Usage: build_source.py <owner> <out_dir>
"""
import html
import json
import os
import subprocess
import sys
import tempfile
import urllib.error
import urllib.request

MAX_VERSIONS = 10

UA = {"User-Agent": "feather-source-builder"}


def fetch_json(url):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.loads(r.read().decode("utf-8"))


def app_entry(base):
    try:
        app = fetch_json(f"{base}/app.json")
        if isinstance(app, dict) and app.get("bundleIdentifier"):
            return app
    except (urllib.error.URLError, ValueError, TimeoutError) as e:
        print(f"  app.json unavailable at {base}: {e}")
    try:
        src = fetch_json(f"{base}/source.json")
        apps = src.get("apps") or []
        if apps:
            return apps[0]
    except (urllib.error.URLError, ValueError, TimeoutError) as e:
        print(f"  source.json unavailable at {base}: {e}")
    return None


def download(url, path):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=120) as r, open(path, "wb") as f:
        while True:
            chunk = r.read(1 << 20)
            if not chunk:
                break
            f.write(chunk)
    return os.path.getsize(path)


def gh(*args):
    return subprocess.run(["gh", *args], capture_output=True, text=True)


def mirror(entry, repo_name, this_repo):
    """Copies the IPA into a release of this repo; returns the permanent URL (or None)."""
    url = entry.get("downloadURL", "")
    version = str(entry.get("version", ""))
    if not url or not version or "/releases/download/" in url:
        return url or None
    asset = url.rsplit("/", 1)[-1]
    tag = f"{repo_name}-{version}"
    permanent = f"https://github.com/{this_repo}/releases/download/{tag}/{asset}"
    view = gh("release", "view", tag, "--repo", this_repo, "--json", "assets", "-q", ".assets[].name")
    if view.returncode == 0 and asset in view.stdout.split():
        return permanent
    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, asset)
        try:
            size = download(url, path)
        except Exception as e:
            print(f"  could not download {url}: {e}")
            return None
        notes = f"{entry.get('name')} {version}: mirrored from {url} for the Feather source."
        if view.returncode == 0:
            r = gh("release", "upload", tag, path, "--repo", this_repo, "--clobber")
        else:
            r = gh("release", "create", tag, path, "--repo", this_repo, "--title", f"{entry.get('name')} {version}",
                   "--notes", notes, "--latest=false")
        if r.returncode != 0:
            print(f"  release upload failed: {r.stderr.strip()}")
            return None
        print(f"  mirrored {asset} ({size} bytes) -> {permanent}")
        entry["size"] = size
    return permanent


def with_history(entry, old):
    """Current version first, then earlier mirrored versions from the live source (permanent URLs only)."""
    current = (entry.get("versions") or [{}])[0]
    current = dict(current)
    current["downloadURL"] = entry["downloadURL"]
    current["size"] = entry.get("size", current.get("size"))
    history = [current]
    for v in (old or {}).get("versions", []):
        if v.get("version") != current.get("version") and "/releases/download/" in str(v.get("downloadURL", "")):
            history.append(v)
    entry["versions"] = history[:MAX_VERSIONS]
    return entry


def main():
    owner, out = sys.argv[1].lower(), sys.argv[2]
    root = f"https://{owner}.github.io"
    here = os.path.dirname(os.path.abspath(__file__))
    with open(os.path.join(here, "..", "apps.json"), encoding="utf-8") as f:
        config = json.load(f)

    previous = {}
    try:
        live = fetch_json(f"{root}/source.json")
        previous = {a.get("bundleIdentifier"): a for a in live.get("apps", [])}
    except Exception as e:  # first deploy, or Pages down
        print(f"No live source to fall back on: {e}")

    this_repo = os.environ.get("GITHUB_REPOSITORY", "")
    apps = []
    featured = []
    for item in config["apps"]:
        base = f"{root}/{item['repo']}"
        print(f"Fetching {base}")
        entry = app_entry(base)
        if entry is None:
            # Fall back to the last published entry for this repo (matched by download URL prefix).
            entry = next((a for a in previous.values() if str(a.get("downloadURL", "")).startswith(base + "/")), None)
            if entry is None:
                print(f"  skipping {item['repo']}: nothing published yet")
                continue
            print("  using the previously published entry")
        entry = dict(entry)
        entry.setdefault("developerName", "SoRadGaming")
        if os.environ.get("MIRROR") == "1" and this_repo:
            permanent = mirror(entry, item["repo"], this_repo)
            if permanent:
                entry["downloadURL"] = permanent
        entry = with_history(entry, previous.get(entry.get("bundleIdentifier")))
        apps.append(entry)
        if item.get("featured"):
            featured.append(entry["bundleIdentifier"])
        print(f"  {entry.get('name')} {entry.get('version')}")

    meta = config["source"]
    os.makedirs(out, exist_ok=True)
    icon = apps[0]["iconURL"] if apps else ""
    if meta.get("iconURL"):
        # Host the source icon ourselves (plain .png URL, no redirects or query strings).
        try:
            download(meta["iconURL"], os.path.join(out, "icon.png"))
            icon = f"{root}/icon.png"
        except Exception as e:
            print(f"Could not fetch source icon: {e}")
            icon = meta["iconURL"]
    source = {
        "name": meta["name"],
        "identifier": meta["identifier"],
        "subtitle": meta.get("subtitle", ""),
        "description": meta.get("description", ""),
        "iconURL": icon,
        "website": root,
        "tintColor": meta.get("tintColor", "FF7A2B"),
        "featuredApps": featured,
        "apps": apps,
        "news": [],
    }
    os.makedirs(out, exist_ok=True)
    with open(os.path.join(out, "source.json"), "w", encoding="utf-8") as f:
        json.dump(source, f, indent=2)
    with open(os.path.join(out, "index.html"), "w", encoding="utf-8") as f:
        f.write(render_page(source, root))
    with open(os.path.join(out, ".nojekyll"), "w") as f:
        f.write("")
    print(f"Wrote {len(apps)} app(s)")


def render_page(source, root):
    url = f"{root}/source.json"
    cards = []
    for a in source["apps"]:
        tint = "#" + str(a.get("tintColor", "FF7A2B")).lstrip("#")
        cards.append(f"""
      <article class="card" style="--tint:{tint}">
        <img class="icon" src="{html.escape(a.get('iconURL', ''))}" alt="" width="72" height="72" loading="lazy">
        <div class="body">
          <h2>{html.escape(a.get('name', ''))}</h2>
          <p class="sub">{html.escape(a.get('subtitle', ''))}</p>
          <p class="desc">{html.escape(a.get('localizedDescription', ''))}</p>
          <p class="meta">Version {html.escape(str(a.get('version', '')))} · iOS {html.escape(str((a.get('versions') or [{}])[0].get('minOSVersion', '17.0')))}+</p>
          <a class="btn" href="{html.escape(a.get('downloadURL', ''))}">Download IPA</a>
        </div>
      </article>""")
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{html.escape(source['name'])}</title>
<style>
  :root {{ --bg:#07070b; --fg:#f2f2f5; --muted:#a3a3b2; --glass:rgba(255,255,255,.07); --edge:rgba(255,255,255,.14); }}
  @media (prefers-color-scheme: light) {{ :root {{ --bg:#eef0f5; --fg:#111118; --muted:#5a5a6a; --glass:rgba(255,255,255,.6); --edge:rgba(0,0,0,.08); }} }}
  * {{ box-sizing:border-box }}
  body {{ margin:0; font:16px/1.5 -apple-system,BlinkMacSystemFont,"SF Pro Text",system-ui,sans-serif; color:var(--fg);
         background:var(--bg); min-height:100vh; }}
  body::before {{ content:""; position:fixed; inset:-20%; z-index:-1;
         background:radial-gradient(40% 35% at 20% 15%, #ff7a2b55, transparent 70%),
                    radial-gradient(35% 30% at 85% 30%, #8b5cf655, transparent 70%),
                    radial-gradient(40% 35% at 50% 95%, #22d3ee33, transparent 70%); filter:blur(30px); }}
  main {{ max-width:760px; margin:0 auto; padding:48px 16px 64px; }}
  h1 {{ font-size:34px; letter-spacing:-.02em; margin:0 0 6px }}
  .lead {{ color:var(--muted); margin:0 0 24px }}
  .glass {{ background:var(--glass); border:1px solid var(--edge); border-radius:24px;
           backdrop-filter:blur(24px) saturate(160%); -webkit-backdrop-filter:blur(24px) saturate(160%);
           box-shadow:0 10px 40px rgba(0,0,0,.25), inset 0 1px 0 rgba(255,255,255,.12); }}
  .source {{ padding:18px; display:flex; gap:12px; align-items:center; flex-wrap:wrap; margin-bottom:28px }}
  .source code {{ flex:1 1 260px; font:14px ui-monospace,SFMono-Regular,Menlo,monospace; word-break:break-all }}
  button, .btn {{ appearance:none; border:0; cursor:pointer; font:600 15px/1 inherit; color:#fff; text-decoration:none;
           padding:12px 18px; border-radius:999px; background:var(--tint,#ff7a2b); display:inline-block;
           box-shadow:inset 0 1px 0 rgba(255,255,255,.35), 0 4px 14px rgba(0,0,0,.25); }}
  .cards {{ display:grid; gap:16px }}
  .card {{ padding:18px; display:flex; gap:16px; align-items:flex-start; }}
  .card {{ background:var(--glass); border:1px solid var(--edge); border-radius:24px;
          backdrop-filter:blur(24px) saturate(160%); -webkit-backdrop-filter:blur(24px) saturate(160%); }}
  .icon {{ border-radius:18px; flex:none; box-shadow:0 6px 18px rgba(0,0,0,.35) }}
  .card h2 {{ margin:0; font-size:20px }}
  .sub {{ margin:2px 0 8px; color:var(--muted) }}
  .desc {{ margin:0 0 8px; font-size:14px }}
  .meta {{ margin:0 0 12px; font-size:13px; color:var(--muted) }}
  ol {{ color:var(--muted); padding-left:20px }}
  @media (max-width:480px) {{ .card {{ flex-direction:column }} }}
</style>
</head>
<body>
<main>
  <h1>{html.escape(source['name'])}</h1>
  <p class="lead">{html.escape(source.get('description', ''))}</p>
  <div class="glass source">
    <code id="u">{html.escape(url)}</code>
    <button onclick="navigator.clipboard.writeText(document.getElementById('u').textContent).then(()=>{{this.textContent='Copied'}})">Copy source URL</button>
  </div>
  <ol>
    <li>Open Feather → Sources → +</li>
    <li>Paste the source URL and add it</li>
    <li>Install any app below; updates appear automatically</li>
  </ol>
  <section class="cards">{''.join(cards)}
  </section>
</main>
</body>
</html>
"""


if __name__ == "__main__":
    main()
