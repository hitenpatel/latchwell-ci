"""Report, and with APPLY=1 set, the App Store metadata of Latchwell's single pre-release version from a JSON file
committed in the app repo (docs/release/app-store-metadata.json). Without APPLY it only reads and prints.
Never submits for review and never touches pricing or availability. Secrets come from env."""
import base64, json, os, sys, time, urllib.request, urllib.error
import jwt

BUNDLE = "app.latchwell.ios"
apply = os.environ.get("APPLY") == "1"
spec = json.load(open(sys.argv[1])) if len(sys.argv) > 1 else {}
key = base64.b64decode(os.environ["ASC_KEY_B64"]).decode()
tok = jwt.encode({"iss": os.environ["ASC_ISSUER_ID"], "iat": int(time.time()), "exp": int(time.time()) + 600, "aud": "appstoreconnect-v1"},
                 key, algorithm="ES256", headers={"kid": os.environ["ASC_KEY_ID"], "typ": "JWT"})
API = "https://api.appstoreconnect.apple.com"

def call(method, path, body=None, fatal=True):
    req = urllib.request.Request(API + path, method=method, data=None if body is None else json.dumps(body).encode(),
                                 headers={"Authorization": f"Bearer {tok}", "Content-Type": "application/json"})
    for attempt in range(6):
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                raw = r.read(); return json.loads(raw) if raw else {}
        except urllib.error.HTTPError as e:
            # App Store Connect returned intermittent 500s on reads (2026-11-17); retry reads only, never writes.
            if method == "GET" and e.code >= 500 and attempt < 5:
                time.sleep(5 * 2 ** attempt); continue
            msg = f"{method} {path.split('?')[0]} -> {e.code}: {e.read()[:600].decode(errors='replace')}"
            if fatal: sys.exit(msg)
            print("  ", msg); return None

def show(label, attrs, keys=None):
    a = attrs or {}
    print(f"{label}:")
    for k in (keys or sorted(a)):
        v = a.get(k); v = (v[:70] + f"... ({len(v)} chars)") if isinstance(v, str) and len(v) > 80 else v
        print(f"    {k} = {v!r}")

apps = call("GET", "/v1/apps?limit=50&fields%5Bapps%5D=bundleId,name,primaryLocale,contentRightsDeclaration")["data"]
app = next(a for a in apps if a["attributes"]["bundleId"] == BUNDLE); A = app["id"]
show("app", app["attributes"])

infos = call("GET", f"/v1/apps/{A}/appInfos?include=primaryCategory,secondaryCategory")
for inf in infos["data"]:
    rel = inf.get("relationships", {})
    print("appInfo", inf["id"][:8], "primary", (rel.get("primaryCategory", {}).get("data") or {}).get("id"),
          "secondary", (rel.get("secondaryCategory", {}).get("data") or {}).get("id"))
info = infos["data"][0]
ilocs = call("GET", f"/v1/appInfos/{info['id']}/appInfoLocalizations")["data"]
for l in ilocs: show(f"appInfoLocalization {l['attributes']['locale']}", l["attributes"], ["name", "subtitle", "privacyPolicyUrl", "privacyChoicesUrl"])
age = call("GET", f"/v1/appInfos/{info['id']}/ageRatingDeclaration", fatal=False)
if age: show("ageRatingDeclaration", age["data"]["attributes"])

vers = call("GET", f"/v1/apps/{A}/appStoreVersions?fields%5BappStoreVersions%5D=versionString")["data"]
if len(vers) != 1: sys.exit(f"expected one pre-release version, found {len(vers)}")
V = vers[0]["id"]
for f in ["copyright", "releaseType", "earliestReleaseDate", "usesIdfa", "downloadable"]:
    r = call("GET", f"/v1/appStoreVersions/{V}?fields%5BappStoreVersions%5D={f}", fatal=False)
    print(f"version.{f} =", None if r is None else r["data"]["attributes"].get(f))
b = call("GET", f"/v1/appStoreVersions/{V}/build", fatal=False)
print("version.build =", b and b.get("data") and b["data"]["attributes"].get("version"))
vlocs = call("GET", f"/v1/appStoreVersions/{V}/appStoreVersionLocalizations")["data"]
for l in vlocs: show(f"versionLocalization {l['attributes']['locale']}", l["attributes"], ["description", "keywords", "promotionalText", "supportUrl", "marketingUrl", "whatsNew"])
rd = call("GET", f"/v1/appStoreVersions/{V}/appStoreReviewDetail", fatal=False)
show("appStoreReviewDetail", (rd or {}).get("data") and rd["data"]["attributes"], ["contactFirstName", "contactLastName", "contactEmail", "contactPhone", "demoAccountRequired", "notes"])

builds = call("GET", f"/v1/builds?filter%5Bapp%5D={A}&limit=5&sort=-uploadedDate&fields%5Bbuilds%5D=version,processingState,uploadedDate,expired")["data"]
for x in builds: print("build", x["attributes"])
iaps = call("GET", f"/v1/apps/{A}/inAppPurchasesV2?limit=20", fatal=False)
for x in (iaps or {}).get("data", []): print("iap", {k: x["attributes"].get(k) for k in ["productId", "name", "inAppPurchaseType", "state"]})
groups = call("GET", f"/v1/apps/{A}/subscriptionGroups?include=subscriptions", fatal=False)
for x in (groups or {}).get("included", []): print("subscription", {k: x["attributes"].get(k) for k in ["productId", "name", "state", "subscriptionPeriod"]})
avail = call("GET", f"/v1/apps/{A}/appAvailabilityV2", fatal=False)
print("availability", avail and avail["data"]["attributes"])
pp = call("GET", f"/v1/apps/{A}/appPricePoints?filter%5Bterritory%5D=GBR&limit=1", fatal=False)
print("price points reachable", bool(pp))

if not apply:
    sys.exit(0)
print("APPLY is not implemented yet"); sys.exit(1)
