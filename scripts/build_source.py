#!/usr/bin/env python3
"""Builds the shared Feather / AltStore source from every app listed in apps.json.

Each app repo publishes its own entry on GitHub Pages:
    https://<owner>.github.io/<repo>/app.json     (preferred)
    https://<owner>.github.io/<repo>/source.json  (fallback: first app in that source)
If an app can't be fetched right now, its entry from the currently live shared source is kept, so a hiccup in one
repo never drops an app from Feather.

Usage: build_source.py <owner> <out_dir>
"""
import html
import json
import os
import sys
import urllib.error
import urllib.request

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
        apps.append(entry)
        if item.get("featured"):
            featured.append(entry["bundleIdentifier"])
        print(f"  {entry.get('name')} {entry.get('version')}")

    meta = config["source"]
    icon = meta.get("iconURL") or (apps[0]["iconURL"] if apps else "")
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
