"""Read-only website checks. No server, network, writes, or background processes."""
import json
from html.parser import HTMLParser
from pathlib import Path
import posixpath
import re
from urllib.parse import urljoin, urlsplit, unquote
ROOT = Path(__file__).resolve().parents[1]
manifest = set(json.loads((ROOT / "deployment/public-files.json").read_text(encoding="utf-8")))
assert len(manifest) == 236
assert all((ROOT / path).is_file() for path in manifest)
assert not (ROOT / "app-icons").exists()
assert (ROOT / "icons").is_dir()
class Document(HTMLParser):
    def __init__(self, name):
        super().__init__()
        self.name, self.ids, self.refs, self.links, self.controls = name, set(), [], [], []
        self.email_count = self.fallback_count = 0
        self.json_script = None
    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if a.get("id"):
            assert a["id"] not in self.ids, (self.name, "duplicate id", a["id"])
            self.ids.add(a["id"])
        if a.get("aria-controls"):
            self.controls += a["aria-controls"].split()
        if tag == "a" and "email-link" in a.get("class", "").split():
            self.email_count += 1
            assert "hidden" in a
            assert not a.get("href", "").startswith("mailto:")
        if "email-fallback" in a.get("class", "").split():
            self.fallback_count += 1
        if tag == "a" and a.get("href"):
            self.links.append(a["href"])
        if tag in {"img", "source", "script"} and a.get("src"):
            self.refs.append(a["src"])
        if tag in {"img", "source"} and a.get("srcset"):
            self.refs += [s.strip().split()[0] for s in a["srcset"].split(",") if s.strip()]
        if tag == "link" and a.get("rel") in {"icon", "apple-touch-icon", "manifest", "stylesheet"}:
            self.refs.append(a["href"])
        if tag == "script" and a.get("type") == "application/ld+json":
            self.json_script = ""
    def handle_data(self, data):
        if self.json_script is not None:
            self.json_script += data
    def handle_endtag(self, tag):
        if tag == "script" and self.json_script is not None:
            json.loads(self.json_script)
            self.json_script = None

address = '@'.join(('my', '.'.join(('schier', 'dk'))))
documents = {}
for path in sorted(ROOT.rglob("*.html")):
    if ".git" in path.parts or "deployment" in path.parts or "tests" in path.parts:
        continue
    name = path.relative_to(ROOT).as_posix()
    text = path.read_text(encoding="utf-8")
    assert address not in text.lower(), name
    assert not re.search(r"document\.documentElement\.classList\.remove\(['\"]no-js", text), name
    doc = Document(name)
    doc.feed(text)
    assert doc.email_count == doc.fallback_count, name
    assert doc.email_count > 0, name
    assert all(item in doc.ids for item in doc.controls), name
    documents[name] = doc
assert len(documents) == 14
count = 0
for name, doc in documents.items():
    for origin in ("http://localhost:8000", "https://www.schier.dk"):
        base = origin + "/" + name
        for reference in doc.refs:
            target = urlsplit(urljoin(base, reference))
            if target.netloc != urlsplit(origin).netloc:
                continue
            local = unquote(target.path).lstrip("/")
            assert local in manifest, (name, reference, local)
            assert (ROOT / local).is_file(), (name, reference)
            count += 1
    # Normal navigation also works when hosted under a subdirectory.
    for prefix in ("", "/preview"):
        base = "https://example.invalid" + prefix + "/" + name
        for href in doc.links:
            if href.startswith(("#", "tel:")):
                continue
            assert not href.startswith("https://www.schier.dk"), (name, href)
            target = urlsplit(urljoin(base, href))
            if target.netloc != "example.invalid":
                continue
            if name == "404.html" and prefix:
                continue  # Apache ErrorDocument is explicitly relative to the domain root.
            assert target.path.startswith(prefix + "/"), (name, prefix, href)
            local = unquote(target.path[len(prefix):]).lstrip("/")
            if (ROOT / local).is_dir():
                local = posixpath.join(local, "index.html")
            assert local in manifest and (ROOT / local).is_file(), (name, prefix, href, local)
            if target.fragment and local in documents:
                assert target.fragment in documents[local].ids, (name, href)
for request in ("/missing/page/", "/missing/page.html", "/ydelser/missing/"):
    for ref in documents["404.html"].refs:
        target = urlsplit(urljoin("https://example.invalid" + request, ref))
        if target.netloc == "example.invalid":
            assert unquote(target.path).lstrip("/") in manifest, (request, ref)
for icon in json.loads((ROOT / "site.webmanifest").read_text(encoding="utf-8"))["icons"]:
    assert icon["src"].lstrip("/") in manifest
css = (ROOT / "css/style.css").read_text(encoding="utf-8")
assert ".no-js .site-nav" in css and ".no-js .nav-toggle" in css
assert re.search(r"\.no-js \.site-nav \.dropdown-menu\s*\{\s*display: block", css)
js = (ROOT / "js/script.js").read_text(encoding="utf-8")
assert address not in js
assert '"icons": {".png"}' in (ROOT / "deployment/sftp_deploy.py").read_text(encoding="utf-8")
print(json.dumps({"HTMLPages": len(documents), "publicFiles": len(manifest),
                  "localResourceReferencesChecked": count, "missingResources": 0,
                  "emailPhoneFallbacks": sum(d.email_count for d in documents.values()),
                  "navigationOrigins": ["localhost", "one.com", "subdirectory preview"],
                  "nested404PathsChecked": 3, "serverStarted": False}))
