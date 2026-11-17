"""Replace the 6.9-inch (APP_IPHONE_67) App Store screenshots of the editable Latchwell version, for every
localization, with the PNGs in DIR (uploaded in filename order). DRY_RUN=1 only reports. Secrets come from env."""
import base64, hashlib, json, os, sys, time, urllib.request, urllib.error
from pathlib import Path
import jwt

BUNDLE, DISPLAY = "app.latchwell.ios", "APP_IPHONE_67"
EDITABLE = {"PREPARE_FOR_SUBMISSION", "DEVELOPER_REJECTED", "REJECTED", "METADATA_REJECTED", "WAITING_FOR_REVIEW", "INVALID_BINARY"}
folder, dry = Path(sys.argv[1]), os.environ.get("DRY_RUN") == "1"
files = sorted(folder.glob("*.png"))
if not files: sys.exit(f"no PNGs in {folder}")
key = base64.b64decode(os.environ["ASC_KEY_B64"]).decode()
tok = jwt.encode({"iss": os.environ["ASC_ISSUER_ID"], "iat": int(time.time()), "exp": int(time.time()) + 600, "aud": "appstoreconnect-v1"},
                 key, algorithm="ES256", headers={"kid": os.environ["ASC_KEY_ID"], "typ": "JWT"})
API = "https://api.appstoreconnect.apple.com"

def call(method, path, body=None, absolute=False):
    req = urllib.request.Request(path if absolute else API + path, method=method,
                                 data=None if body is None else json.dumps(body).encode(),
                                 headers={"Authorization": f"Bearer {tok}", "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            raw = r.read(); return json.loads(raw) if raw else {}
    except urllib.error.HTTPError as e:
        sys.exit(f"{method} {path.split('?')[0]} -> {e.code}: {e.read()[:400].decode(errors='replace')}")

# GET /v1/apps returned 500 for this key on 2026-11-17 while /v1/bundleIds worked, so find the app through its bundle ID.
bid = call("GET", f"/v1/bundleIds?filter%5Bidentifier%5D={BUNDLE}&include=app")
app = next(i for i in bid.get("included", []) if i["type"] == "apps")
vers = call("GET", f"/v1/apps/{app['id']}/appStoreVersions?filter%5Bplatform%5D=IOS&limit=10")["data"]
for v in vers: print("version", v["attributes"]["versionString"], v["attributes"]["appStoreState"])
ver = next((v for v in vers if v["attributes"]["appStoreState"] in EDITABLE), None)
if not ver: sys.exit("no editable App Store version")
print("using version", ver["attributes"]["versionString"])
locs = call("GET", f"/v1/appStoreVersions/{ver['id']}/appStoreVersionLocalizations")["data"]
for f in files: print("file", f.name, f.stat().st_size, "bytes")
for loc in locs:
    lang = loc["attributes"]["locale"]
    sets = call("GET", f"/v1/appStoreVersionLocalizations/{loc['id']}/appScreenshotSets")["data"]
    s = next((x for x in sets if x["attributes"]["screenshotDisplayType"] == DISPLAY), None)
    existing = call("GET", f"/v1/appScreenshotSets/{s['id']}/appScreenshots")["data"] if s else []
    print(f"{lang}: set {'exists' if s else 'missing'}, {len(existing)} screenshots now")
    if dry: continue
    if not s:
        s = call("POST", "/v1/appScreenshotSets", {"data": {"type": "appScreenshotSets", "attributes": {"screenshotDisplayType": DISPLAY},
             "relationships": {"appStoreVersionLocalization": {"data": {"type": "appStoreVersionLocalizations", "id": loc["id"]}}}}})["data"]
    for old in existing: call("DELETE", f"/v1/appScreenshots/{old['id']}")
    ids = []
    for f in files:
        data = f.read_bytes()
        shot = call("POST", "/v1/appScreenshots", {"data": {"type": "appScreenshots", "attributes": {"fileName": f.name, "fileSize": len(data)},
               "relationships": {"appScreenshotSet": {"data": {"type": "appScreenshotSets", "id": s["id"]}}}}})["data"]
        for op in shot["attributes"]["uploadOperations"]:
            part = data[op["offset"]: op["offset"] + op["length"]]
            req = urllib.request.Request(op["url"], method=op["method"], data=part, headers={h["name"]: h["value"] for h in op["requestHeaders"]})
            urllib.request.urlopen(req, timeout=120).read()
        call("PATCH", f"/v1/appScreenshots/{shot['id']}", {"data": {"type": "appScreenshots", "id": shot["id"],
             "attributes": {"uploaded": True, "sourceFileChecksum": hashlib.md5(data).hexdigest()}}})
        ids.append(shot["id"]); print(f"  uploaded {f.name}")
    call("PATCH", f"/v1/appScreenshotSets/{s['id']}/relationships/appScreenshots", {"data": [{"type": "appScreenshots", "id": i} for i in ids]})
    print(f"{lang}: {len(ids)} screenshots in order")
