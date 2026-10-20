#!/usr/bin/env python3
"""Manual, manifest-only, non-deleting SFTP publication. No remote shell commands."""
from __future__ import annotations

import argparse
import base64
from contextlib import suppress
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
import errno
import hashlib
import hmac
import html
import json
import logging
import os
from pathlib import Path, PurePosixPath
import posixpath
import re
import stat
import subprocess
import sys
import tempfile
import urllib.request
import uuid

import paramiko

REPO = Path(__file__).resolve().parents[1]
MANIFEST = REPO / "deployment" / "public-files.json"
KNOWN_HOSTS = REPO / "deployment" / "known_hosts"
MAX_FILE = 32 * 1024 * 1024
MAX_TOTAL = 256 * 1024 * 1024
WORKFLOW = ".github/workflows/deploy.yml"
PRODUCTION_ROOT = "/customers/7/7/4/cmcay2ntn/webroots/www"
PREVIEW_ROOT = "/customers/7/7/4/cmcay2ntn/webroots/df12bd7c"
PREVIEW_ALIAS = "/webroots/df12bd7c"
ALLOWED_ROOT = {".htaccess", "404.html", "index.html", "favicon.ico",
                "robots.txt", "site.webmanifest", "sitemap.xml"}
ALLOWED_EXTENSIONS = {
    "css": {".css"},
    "js": {".js"},
    "images": {".avif", ".jpg", ".png", ".svg", ".webp"},
}
PROTECTED_NAMES = {"uploads", "upload", "backups", "backup", "logs",
                   "cache", "private", "httpd.private", "node_modules",
                   "vendor", "deployment", "docs", "tests"}


class SafeError(Exception):
    """A fixed, credential-free error suitable for the job summary."""


@dataclass(frozen=True)
class PublicFile:
    path: str
    content: bytes
    sha256: str


@dataclass(frozen=True)
class Config:
    host: str
    user: str
    password: str = field(repr=False)
    fingerprint: str
    remote_dir: str
    root_confirmed: bool
    port: int = 22
    target: str = "Production"


class PinnedHostKey(paramiko.MissingHostKeyPolicy):
    """Compare the SSH key BEFORE password authentication; never trust on first use."""
    def __init__(self, fingerprint: str):
        self.fingerprint = fingerprint

    def missing_host_key(self, client, hostname, key):
        actual = "SHA256:" + base64.b64encode(
            hashlib.sha256(key.asbytes()).digest()
        ).decode("ascii").rstrip("=")
        if not hmac.compare_digest(actual, self.fingerprint):
            raise SafeError("SSH host key mismatch. Stop and verify the change with one.com; never replace the pin automatically.")
        # Do not add or save keys. This exact fingerprint is the sole trust anchor.


def pinned_identity():
    """The only trust anchor is the ED25519 public key committed to this repository."""
    try:
        lines = [line.strip() for line in KNOWN_HOSTS.read_text(encoding="utf-8").splitlines()
                 if line.strip() and not line.lstrip().startswith("#")]
        if len(lines) != 1:
            raise ValueError
        host, algorithm, encoded = lines[0].split()
        if algorithm != "ssh-ed25519" or not re.fullmatch(r"[A-Za-z0-9.-]+", host):
            raise ValueError
        raw = base64.b64decode(encoded, validate=True)
        paramiko.Ed25519Key(data=raw)  # Validate the full SSH public-key encoding.
    except (OSError, ValueError, paramiko.SSHException):
        raise SafeError("Missing or invalid repository-pinned ED25519 known_hosts key.") from None
    fingerprint = "SHA256:" + base64.b64encode(hashlib.sha256(raw).digest()).decode().rstrip("=")
    return host, fingerprint


def openssh_preflight(config: Config):
    """Read-only SFTP session with literal OpenSSH StrictHostKeyChecking=yes.

    Called only after the main/run/receipt guards. Authentication uses an ephemeral
    ASKPASS helper referencing the environment; no password is stored or logged.
    No shell session or remote shell command is opened.
    """
    if sys.platform != "linux":
        raise SafeError("The strict OpenSSH preflight is intended for the Linux Actions runner.")
    with tempfile.TemporaryDirectory(prefix="sftp-askpass-") as folder:
        helper = Path(folder) / "askpass.py"
        helper.write_text(
            "#!" + sys.executable + "\n"
            "import os, sys\n"
            "sys.stdout.write(os.environ['SFTP_PASSWORD'] + '\\n')\n",
            encoding="utf-8",
        )
        helper.chmod(0o700)
        environment = os.environ.copy()
        environment.pop("GH_TOKEN", None)
        environment.pop("GITHUB_TOKEN", None)
        environment.update(
            SSH_ASKPASS=str(helper), SSH_ASKPASS_REQUIRE="force",
            DISPLAY="sftp-askpass", SFTP_PASSWORD=config.password,
        )
        command = [
            "/usr/bin/sftp", "-F", "/dev/null", "-P", str(config.port),
            "-oStrictHostKeyChecking=yes",
            "-oUserKnownHostsFile=" + str(KNOWN_HOSTS),
            "-oGlobalKnownHostsFile=/dev/null",
            "-oHostKeyAlgorithms=ssh-ed25519",
            "-oVerifyHostKeyDNS=no", "-oUpdateHostKeys=no", "-oCheckHostIP=no",
            "-oBatchMode=no", "-oNumberOfPasswordPrompts=1",
            "-oPreferredAuthentications=password", "-oPasswordAuthentication=yes",
            "-oPubkeyAuthentication=no", "-oIdentityAgent=none",
            "-oConnectTimeout=20", "-oServerAliveInterval=15",
            "-oServerAliveCountMax=2", "-oLogLevel=ERROR",
            "-oUser=" + config.user,
            "-b", "-", "--", config.host,
        ]
        try:
            result = subprocess.run(
                command, input="pwd\nquit\n", text=True, env=environment,
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                timeout=75, check=False,
            )
        except (OSError, subprocess.SubprocessError):
            raise SafeError("Strict OpenSSH SFTP verification failed; no transfer attempted.") from None
        if result.returncode != 0:
            raise SafeError(
                "Strict OpenSSH SFTP connection rejected (host key, authentication or network). "
                "The pin was not changed and no transfer was attempted."
            )


def connect(config: Config):
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(PinnedHostKey(config.fingerprint))
    try:
        client.connect(
            config.host, port=config.port, username=config.user,
            password=config.password, allow_agent=False, look_for_keys=False,
            timeout=20, banner_timeout=20, auth_timeout=20, channel_timeout=30,
        )
        sftp = client.open_sftp()
        sftp.get_channel().settimeout(30)
        return client, sftp
    except Exception:
        client.close()
        raise


def allowed_public_path(path: str) -> bool:
    if not isinstance(path, str) or not re.fullmatch(r"[A-Za-z0-9_./-]+", path):
        return False
    parts = path.split("/")
    if any(p in {"", ".", ".."} for p in parts):
        return False
    if path in ALLOWED_ROOT:
        return True
    if any(p.startswith(".") or p.lower() in PROTECTED_NAMES or
           p.lower() == "desktop.ini" for p in parts):
        # Four known .htaccess files are allowed explicitly below.
        return path in {"kontakt/.htaccess", "om-os/.htaccess", "ydelser/.htaccess"}
    top = parts[0]
    if top in ALLOWED_EXTENSIONS:
        return len(parts) > 1 and PurePosixPath(path).suffix.lower() in ALLOWED_EXTENSIONS[top]
    if top in {"kontakt", "om-os"}:
        return path == top + "/index.html"
    if top == "ydelser":
        return path == "ydelser/index.html" or (
            len(parts) == 3 and parts[-1] == "index.html"
        )
    return False


def load_public_files(repo: Path = REPO, manifest: Path = MANIFEST):
    try:
        names = json.loads(manifest.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        raise SafeError("Cannot read deployment/public-files.json.") from None
    if not isinstance(names, list) or not names or len(names) > 2000:
        raise SafeError("The publication manifest must be a non-empty list (max 2000 files).")
    if any(not isinstance(n, str) or not allowed_public_path(n) for n in names):
        raise SafeError("Manifest contains a non-public, protected or unsafe path.")
    if len(set(names)) != len(names) or len({n.casefold() for n in names}) != len(names):
        raise SafeError("Duplicate/case-colliding publication paths.")
    if not {"index.html", ".htaccess", "site.webmanifest"}.issubset(names):
        raise SafeError("The manifest is missing required website files.")
    tracked_result = subprocess.run(
        ["git", "-C", str(repo), "ls-files", "--stage", "-z"],
        check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    )
    tracked = {}
    for record in tracked_result.stdout.split(b"\0"):
        if record:
            meta, path = record.decode("utf-8").split("\t", 1)
            mode, _, stage = meta.split()
            if stage != "0":
                raise SafeError("Unmerged Git index.")
            tracked[path] = mode
    files = []
    total = 0
    for name in sorted(names):
        if tracked.get(name) not in {"100644", "100755"}:
            raise SafeError("A public manifest entry is untracked or is a symbolic link.")
        path = repo / name
        if any(p.is_symlink() for p in [path, *path.parents] if p != repo.parent):
            raise SafeError("Local symlinks are not allowed for public files.")
        if not path.is_file() or path.stat().st_size > MAX_FILE:
            raise SafeError("A public file is missing, not regular, or exceeds 32 MiB.")
        data = path.read_bytes()
        if len(data) > MAX_FILE:
            raise SafeError("A public file grew beyond 32 MiB while being read.")
        total += len(data)
        if total > MAX_TOTAL:
            raise SafeError("Publication exceeds the 256 MiB safety limit.")
        files.append(PublicFile(name, data, hashlib.sha256(data).hexdigest()))
    return files


def manifest_digest(files):
    return hashlib.sha256(json.dumps(
        [(f.path, f.sha256) for f in files], separators=(",", ":")
    ).encode("utf-8")).hexdigest()


def load_config() -> Config:
    required = ("SFTP_HOST", "SFTP_USER", "SFTP_PASSWORD")
    if any(not os.environ.get(n, "").strip() for n in required):
        raise SafeError(
            "Missing SFTP login secrets. No connection attempted."
        )
    pinned_host, fingerprint = pinned_identity()
    optional_pin = os.environ.get("SFTP_HOST_KEY_SHA256", "").strip()
    if optional_pin and not hmac.compare_digest(optional_pin, fingerprint):
        raise SafeError("Optional fingerprint variable disagrees with repository-pinned host key.")
    target = os.environ.get("SFTP_TARGET", "Production")
    if target not in {"Production", "Preview"}:
        raise SafeError("Unknown deployment target.")
    prefix = "SFTP_PREVIEW" if target == "Preview" else "SFTP"
    remote_dir = os.environ.get(prefix + "_REMOTE_DIR", "").strip()
    if target == "Preview" and remote_dir not in {PREVIEW_ROOT, PREVIEW_ALIAS}:
        raise SafeError("Preview requires the owner-confirmed df12bd7c webroot; production fallback is forbidden.")
    if target == "Production" and remote_dir in {PREVIEW_ROOT, PREVIEW_ALIAS}:
        raise SafeError("The preview root cannot be used as a Production target.")
    if remote_dir and (
        not remote_dir.startswith("/") or "\\" in remote_dir or
        any(ord(c) < 32 or ord(c) == 127 for c in remote_dir) or
        ".." in remote_dir.split("/") or posixpath.normpath(remote_dir) != remote_dir
        or remote_dir.startswith("//")
    ):
        raise SafeError("SFTP_REMOTE_DIR must be an explicit normalized absolute SFTP path.")
    host = os.environ["SFTP_HOST"].strip()
    if not re.fullmatch(r"[A-Za-z0-9.-]+", host):
        raise SafeError("SFTP_HOST must be a hostname, without scheme, port, or path.")
    if host != pinned_host:
        raise SafeError("SFTP_HOST is not the hostname pinned in deployment/known_hosts.")
    return Config(host, os.environ["SFTP_USER"], os.environ["SFTP_PASSWORD"],
                  fingerprint, remote_dir,
                  os.environ.get(prefix + "_ROOT_CONFIRMED", "") == "true",
                  target=target)


def configuration_digest(config: Config, files):
    # Deliberately excludes the password. No password or password hash is recorded.
    data = [config.host, config.user, config.port, config.fingerprint,
            config.remote_dir, config.target, manifest_digest(files)]
    return hashlib.sha256(json.dumps(data, separators=(",", ":")).encode()).hexdigest()


def lstat_or_none(sftp, path):
    try:
        return sftp.lstat(path)
    except OSError as exc:
        if exc.errno == errno.ENOENT:
            return None
        raise


def check_remote_path(sftp, path, *, allow_missing=False):
    """lstat every component; never follow a symlink into an unrelated directory."""
    current = "/"
    components = PurePosixPath(path).parts[1:]
    if not components:
        info = sftp.lstat("/")
        if not stat.S_ISDIR(info.st_mode):
            raise SafeError("SFTP root is not a directory.")
        return info
    for i, component in enumerate(components):
        current = posixpath.join(current, component)
        info = lstat_or_none(sftp, current)
        if info is None:
            if allow_missing:
                return None
            raise SafeError("A required remote directory/file is missing.")
        if stat.S_ISLNK(info.st_mode):
            raise SafeError("Remote symlink encountered; publication blocked.")
        if i < len(components) - 1 and not stat.S_ISDIR(info.st_mode):
            raise SafeError("Remote ancestor is not a directory.")
    return info


def remote_hash(sftp, path):
    info = check_remote_path(sftp, path, allow_missing=True)
    if info is None:
        return None, None
    if not stat.S_ISREG(info.st_mode):
        raise SafeError("A public remote path is not a regular file.")
    if info.st_size > MAX_FILE:
        raise SafeError("A remote public file exceeds the 32 MiB comparison limit.")
    digest = hashlib.sha256()
    count = 0
    with sftp.open(path, "rb") as handle:
        while True:
            block = handle.read(65536)
            if not block:
                break
            count += len(block)
            if count > MAX_FILE:
                raise SafeError("Remote file grew beyond the comparison limit.")
            digest.update(block)
    after = sftp.lstat(path)
    if (count != info.st_size or after.st_size != info.st_size or
            after.st_mtime != info.st_mtime or not stat.S_ISREG(after.st_mode)):
        raise SafeError("A remote file changed during comparison. Repeat Test.")
    return digest.hexdigest(), stat.S_IMODE(info.st_mode) & 0o777


def validate_root(sftp, remote_dir):
    canonical = sftp.normalize(remote_dir)
    if not canonical.startswith("/") or posixpath.normpath(canonical) != canonical:
        raise SafeError("Server returned an invalid canonical SFTP path.")
    info = check_remote_path(sftp, remote_dir)
    if not stat.S_ISDIR(info.st_mode):
        raise SafeError("Configured remote root is not a directory.")
    check_remote_path(sftp, canonical)
    index = posixpath.join(canonical, "index.html")
    info = check_remote_path(sftp, index)
    if not stat.S_ISREG(info.st_mode) or info.st_size > 2 * 1024 * 1024:
        raise SafeError("Remote root has no small regular index.html to identify schier.dk.")
    with sftp.open(index, "rb") as handle:
        content = handle.read(2 * 1024 * 1024 + 1)
    if b"https://www.schier.dk/" not in content:
        raise SafeError("Remote index.html does not identify schier.dk. Confirm the correct webroot.")
    return canonical


def publication_files(files, config):
    """Bind indexing policy to the target, never to the source robots.txt."""
    if config.target == "Production":
        production_robots = (REPO / "deployment" / "production-robots.txt").read_bytes()
        expected = (b"User-agent: *\nAllow: /\nDisallow:\n\n"
                    b"Sitemap: https://www.schier.dk/sitemap.xml\n")
        if production_robots != expected:
            raise SafeError("Production robots policy changed or blocks indexing; publication is forbidden.")
        if any(f.path == ".htaccess" and b"noindex" in f.content.lower() for f in files):
            raise SafeError("Production .htaccess must never contain a noindex rule.")
        replacements = {"robots.txt": production_robots}
    elif config.target == "Preview":
        replacements = {
            ".htaccess": (REPO / "deployment" / "preview.htaccess").read_bytes(),
            "robots.txt": b"# Source/Preview: pages use noindex; allow crawlers to read that rule.\nUser-agent: *\nDisallow:\n",
        }
    else:
        raise SafeError("Unknown deployment target.")
    result = []
    for file in files:
        content = replacements.get(file.path, file.content)
        if config.target == "Production" and file.path.endswith(".html") and file.path != "404.html":
            content, count = re.subn(
                rb'(<meta name="robots" content=")noindex,nofollow("\s*/>)',
                rb'\g<1>index,follow,max-image-preview:large\2', content,
            )
            if count != 1:
                raise SafeError("Production HTML must receive exactly one verified index/follow rule.")
        result.append(PublicFile(file.path, content, hashlib.sha256(content).hexdigest()))
    return result


def validate_target_root(sftp, config):
    if config.target == "Production":
        return validate_root(sftp, config.remote_dir)
    if (config.target != "Preview" or not config.root_confirmed or
            config.remote_dir not in {PREVIEW_ROOT, PREVIEW_ALIAS}):
        raise SafeError("Preview root has not been explicitly confirmed.")
    canonical = sftp.normalize(config.remote_dir)
    if canonical != PREVIEW_ROOT or canonical == PRODUCTION_ROOT:
        raise SafeError("Preview resolved outside its sole approved webroot. No upload permitted.")
    for path in {config.remote_dir, canonical}:
        info = check_remote_path(sftp, path)
        if not stat.S_ISDIR(info.st_mode):
            raise SafeError("Preview webroot must already exist as a real directory.")
    # New subdomains may be empty or contain a provider default index. This exact
    # root is owner-confirmed; do not require a production index or create a root.
    return canonical


def discover_roots(sftp):
    """Read-only hints only; never select a root or produce a passing Test receipt."""
    landing = sftp.normalize(".")
    candidates = []
    try:
        validate_root(sftp, landing)
        candidates.append(landing)
    except (SafeError, OSError):
        pass
    checked = 0
    for info in sftp.listdir_iter(".", read_aheads=1):
        if checked >= 30:
            break
        if (not stat.S_ISDIR(info.st_mode) or info.filename.startswith(".") or
                info.filename.lower() in PROTECTED_NAMES):
            continue
        checked += 1
        candidate = posixpath.join(landing, info.filename)
        try:
            root = validate_root(sftp, candidate)
            if root not in candidates:
                candidates.append(root)
        except (SafeError, OSError):
            pass
    return {"landing_directory": landing, "possible_webroots": candidates,
            "note": "Read-only hints, at most 30 child directories; no root selected or confirmed."}


def compare_files(sftp, root, files):
    rows = []
    for file in files:
        row = {"path": file.path, "status": "", "local_sha256": file.sha256,
               "remote_sha256": None, "bytes": len(file.content)}
        try:
            sha, mode = remote_hash(sftp, posixpath.join(root, file.path))
            row["remote_sha256"] = sha
            row["remote_mode"] = mode
            row["status"] = "NEW" if sha is None else (
                "UNCHANGED" if hmac.compare_digest(sha, file.sha256) else "CHANGED"
            )
        except SafeError as exc:
            row.update(status="ERROR", error=str(exc))
        except (OSError, paramiko.SSHException):
            row.update(status="ERROR", error="Cannot safely read/stat this remote file.")
        rows.append(row)
    return rows


def preserved_root_entries(sftp, root, files):
    managed = {f.path.split("/")[0] for f in files}
    entries = []
    for info in sftp.listdir_iter(root, read_aheads=1):
        if info.filename not in managed:
            entries.append(info.filename)
        if len(entries) >= 200:
            entries.append("[listing limited to 200 unmanaged root entries]")
            break
    return sorted(entries)


def ensure_parent(sftp, root, relative):
    parent_parts = PurePosixPath(relative).parts[:-1]
    current = root
    for component in parent_parts:
        current = posixpath.join(current, component)
        info = check_remote_path(sftp, current, allow_missing=True)
        if info is None:
            sftp.mkdir(current, mode=0o755)
            info = check_remote_path(sftp, current)
        if not stat.S_ISDIR(info.st_mode):
            raise SafeError("Remote publication parent is not a directory.")


def deploy_files(sftp, root, files, rows, *, preview=False):
    """All comparison errors stop publication BEFORE any upload/mkdir/rename."""
    if any(row["status"] == "ERROR" for row in rows):
        raise SafeError("Comparison has errors; no upload was attempted.")
    sources = {file.path: file for file in files}
    # Every file is compared before the first write. Recheck changed/new targets too.
    def publication_order(row):
        path = row["path"]
        priority = (-1 if preview and path == ".htaccess" else
                    3 if path.endswith(".htaccess") else
                    2 if path.endswith(".html") else
                    1 if path in {"site.webmanifest", "robots.txt", "sitemap.xml"} else 0)
        return priority, path
    for row in sorted(rows, key=publication_order):
        if row["status"] == "UNCHANGED":
            continue
        target = posixpath.join(root, row["path"])
        current, _ = remote_hash(sftp, target)
        if current != row["remote_sha256"]:
            raise SafeError("A deployment target changed after comparison. Stop and repeat Test.")
        file = sources[row["path"]]
        ensure_parent(sftp, root, row["path"])
        temporary = posixpath.join(posixpath.dirname(target),
                                   ".sftp-deploy-" + uuid.uuid4().hex + ".tmp")
        row["upload_state"] = "STARTED"
        # Exclusive temporary file. Never truncate the current live file.
        with sftp.open(temporary, "wx") as handle:
            handle.write(file.content)
            handle.flush()
        sftp.chmod(temporary, row["remote_mode"] if row["remote_mode"] is not None else 0o644)
        uploaded, _ = remote_hash(sftp, temporary)
        if uploaded != file.sha256:
            raise SafeError("Temporary upload verification failed; live target was not replaced.")
        current, _ = remote_hash(sftp, target)
        if current != row["remote_sha256"]:
            raise SafeError("Remote target changed during upload; live target was not replaced.")
        if row["status"] == "NEW":
            # Standard SFTP rename must refuse an already existing destination.
            sftp.rename(temporary, target)
        else:
            # Requires OpenSSH posix-rename extension, no shell. Never use a delete fallback.
            sftp.posix_rename(temporary, target)
        row["upload_state"] = "PUBLISHED"
        verified, _ = remote_hash(sftp, target)
        if verified != file.sha256:
            raise SafeError("Published file failed verification. Inspect the report immediately.")
        row["upload_state"] = "VERIFIED"
    # There is deliberately no remove/unlink/rmdir, recursive mirror, or remote shell.


def github_json(path):
    if not re.fullmatch(r"/repos/[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+/[A-Za-z0-9_./-]+", path):
        raise SafeError("Unsafe GitHub API path.")
    request = urllib.request.Request(
        "https://api.github.com" + path,
        headers={"Accept": "application/vnd.github+json",
                 "Authorization": "Bearer " + os.environ["GH_TOKEN"],
                 "X-GitHub-Api-Version": "2022-11-28",
                 "User-Agent": "schier-sftp-deployment"},
    )
    # GitHub repository is fixed by the trusted workflow context, not an input URL.
    class NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, req, fp, code, msg, headers, newurl):
            return None
    # Never forward the GITHUB_TOKEN to an artifact/CDN or a redirect target.
    opener = urllib.request.build_opener(NoRedirect())
    with opener.open(request, timeout=30) as response:
        return json.load(response)


def assert_current_main():
    if (os.environ.get("GITHUB_ACTIONS") != "true" or
            os.environ.get("GITHUB_EVENT_NAME") != "workflow_dispatch" or
            os.environ.get("GITHUB_REF") != "refs/heads/main"):
        raise SafeError("Only GitHub Actions workflow_dispatch on main is permitted.")
    repo = os.environ["GITHUB_REPOSITORY"]
    sha = github_json(f"/repos/{repo}/git/ref/heads/main")["object"]["sha"]
    if sha != os.environ["GITHUB_SHA"]:
        raise SafeError("This run is no longer the current main commit. Start a new Test.")


def make_receipt(config, files, canonical_root):
    return {
        "schema": 1, "mode": "Test", "repository": os.environ["GITHUB_REPOSITORY"],
        "commit": os.environ["GITHUB_SHA"], "run_id": os.environ["GITHUB_RUN_ID"],
        "run_attempt": os.environ["GITHUB_RUN_ATTEMPT"],
        "created_at": datetime.now(timezone.utc).isoformat(),
        "configuration_sha256": configuration_digest(config, files),
        "manifest_sha256": manifest_digest(files),
        "canonical_root": canonical_root, "file_count": len(files),
        "comparison_complete": True, "remote_writes": 0,
    }


def validate_receipt(receipt, config, files, run_id, metadata, now=None):
    now = now or datetime.now(timezone.utc)
    try:
        created = datetime.fromisoformat(receipt["created_at"])
        correct = (
            receipt["schema"] == 1 and receipt["mode"] == "Test" and
            receipt["repository"] == os.environ["GITHUB_REPOSITORY"] and
            receipt["commit"] == os.environ["GITHUB_SHA"] and
            receipt["run_id"] == run_id and
            receipt["run_attempt"] == str(metadata["run_attempt"]) and
            receipt["configuration_sha256"] == configuration_digest(config, files) and
            receipt["manifest_sha256"] == manifest_digest(files) and
            receipt["file_count"] == len(files) and
            receipt["comparison_complete"] is True and receipt["remote_writes"] == 0 and
            metadata["id"] == int(run_id) and metadata["status"] == "completed" and
            metadata["conclusion"] == "success" and
            metadata["event"] == "workflow_dispatch" and
            metadata["head_branch"] == "main" and
            metadata["head_sha"] == os.environ["GITHUB_SHA"] and
            metadata["path"] == WORKFLOW and
            metadata["head_repository"]["full_name"] == os.environ["GITHUB_REPOSITORY"] and
            created.tzinfo is not None and timedelta(0) <= now - created <= timedelta(hours=24)
        )
    except (KeyError, TypeError, ValueError):
        correct = False
    if not correct:
        raise SafeError("Deploy requires a successful Test of this commit/configuration within 24 hours.")


def read_test_receipt(path, config, files):
    run_id = os.environ.get("SFTP_TEST_RUN_ID", "")
    if not run_id.isdecimal() or run_id == os.environ["GITHUB_RUN_ID"]:
        raise SafeError("Missing or invalid earlier Test run ID.")
    try:
        if path.stat().st_size > 16384:
            raise ValueError
        receipt = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        raise SafeError("The earlier Test receipt is missing or invalid.") from None
    repo = os.environ["GITHUB_REPOSITORY"]
    metadata = github_json(f"/repos/{repo}/actions/runs/{run_id}")
    validate_receipt(receipt, config, files, run_id, metadata)
    return receipt


def write_report(directory, report):
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "report.json").write_text(
        json.dumps(report, indent=2, ensure_ascii=True) + "\n", encoding="utf-8"
    )
    escape = lambda value: html.escape(str(value)).replace("|", "&#124;").replace("\n", " ")
    counts = Counter(row["status"] for row in report["files"])
    lines = [
        "# one.com SFTP — " + escape(report["mode"]),
        "", "**Result:** " + escape(report["result"]), "",
        "Target: " + escape(report.get("target", "Production")),
        "Remote root: " + escape(report.get("canonical_root", "not verified")), "",
        "Content is compared using SHA-256, including files of equal size. No mtime-only assumptions.",
        "No remote deletion commands exist. Server-only files are preserved.",
        "", f"NEW: {counts['NEW']} · CHANGED: {counts['CHANGED']} · "
            f"UNCHANGED: {counts['UNCHANGED']} · ERROR: {counts['ERROR']}", "",
    ]
    if report.get("error"):
        lines += ["**Error:** " + escape(report["error"]), ""]
    if "discovery" in report:
        lines += ["## Read-only webroot hints", "",
                  "<pre>" + html.escape(json.dumps(report["discovery"], indent=2)) + "</pre>", ""]
    if report.get("preserved_root_entries"):
        lines += ["## Unmanaged root entries (preserved; contents not inventoried)", ""]
        lines += ["- " + escape(json.dumps(p)) for p in report["preserved_root_entries"]]
        lines += [""]
    lines += ["## Public files", "", "| File | Comparison | Upload |",
              "|---|---|---|"]
    for row in report["files"]:
        lines.append("| " + escape(row["path"]) + " | " + escape(row["status"]) +
                     " | " + escape(row.get("upload_state", "not uploaded")) + " |")
        if row.get("error"):
            lines.append("| ↳ " + escape(row["error"]) + " | ERROR | |")
    lines += ["", "An interrupted Deploy may have published only part of the plan.",
              "An unsupported atomic-rename extension leaves the previous live target intact.",
              "Failed Deploys may leave hidden .sftp-deploy-*.tmp files; no automatic cleanup/deletion.",
              "Do not edit the site manually on the server while a Deploy is running.", ""]
    text = "\n".join(lines)
    (directory / "summary.md").write_text(text, encoding="utf-8")
    if os.environ.get("GITHUB_STEP_SUMMARY"):
        with open(os.environ["GITHUB_STEP_SUMMARY"], "a", encoding="utf-8") as handle:
            handle.write(text)
    # Never print raw exception text, server banners, usernames, hosts, or passwords.
    print(f"SFTP {report['mode']}: {report['result']}; "
          f"new={counts['NEW']}, changed={counts['CHANGED']}, "
          f"unchanged={counts['UNCHANGED']}, errors={counts['ERROR']}")


def run(mode, report_dir, test_receipt):
    logging.disable(logging.CRITICAL)
    report = {"mode": mode, "result": "FAILED", "files": []}
    client = sftp = None
    try:
        files = load_public_files()
        config = load_config()
        report["target"] = config.target
        files = publication_files(files, config)
        assert_current_main()
        receipt = None
        if mode == "Deploy":
            if not config.remote_dir or not config.root_confirmed:
                raise SafeError("Deploy blocked: confirm SFTP_REMOTE_DIR and set SFTP_ROOT_CONFIRMED=true.")
            receipt = read_test_receipt(test_receipt, config, files)
        openssh_preflight(config)
        report["host_key_trust"] = "TOFU_PINNED_ED25519"
        report["openssh_strict_host_key_checking"] = "yes"
        client, sftp = connect(config)
        if not config.remote_dir:
            report["discovery"] = discover_roots(sftp)
            raise SafeError("No remote root configured. Hints are NOT a completed comparison; Deploy stays blocked.")
        root = validate_target_root(sftp, config)
        report["canonical_root"] = root
        report["files"] = compare_files(sftp, root, files)
        report["preserved_root_entries"] = preserved_root_entries(sftp, root, files)
        if any(row["status"] == "ERROR" for row in report["files"]):
            raise SafeError("Comparison is incomplete. No files were uploaded.")
        if not config.root_confirmed:
            raise SafeError("Comparison completed read-only; confirm this webroot before a passing Test.")
        if mode == "Deploy":
            if root != receipt["canonical_root"]:
                raise SafeError("Canonical remote root differs from the earlier Test.")
            assert_current_main()
            deploy_files(sftp, root, files, report["files"], preview=config.target == "Preview")
            report["result"] = "DEPLOYED_AND_VERIFIED"
        else:
            report_dir.mkdir(parents=True, exist_ok=True)
            (report_dir / "test-receipt.json").write_text(
                json.dumps(make_receipt(config, files, root), indent=2) + "\n",
                encoding="utf-8",
            )
            report["result"] = "TEST_PASSED_READ_ONLY"
    except SafeError as exc:
        report["error"] = str(exc)
    except paramiko.AuthenticationException:
        report["error"] = "SFTP authentication failed. Check the three GitHub secrets."
    except (OSError, paramiko.SSHException, ValueError, KeyError, subprocess.SubprocessError):
        report["error"] = ("Connection, configuration, API or SFTP operation failed. "
                           "No raw server exception is logged to avoid disclosing credentials. "
                           "Check upload states; a Deploy may be partial.")
    except Exception:
        report["error"] = "Unexpected failure; details suppressed to protect credentials. Inspect the local code/tests."
    finally:
        if sftp:
            with suppress(Exception):
                sftp.close()
        if client:
            with suppress(Exception):
                client.close()
        write_report(report_dir, report)
    return 0 if report["result"] in {"TEST_PASSED_READ_ONLY", "DEPLOYED_AND_VERIFIED"} else 1


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=["Test", "Deploy"], required=True)
    parser.add_argument("--report-dir", type=Path, required=True)
    parser.add_argument("--test-receipt", type=Path, required=True)
    args = parser.parse_args()
    sys.exit(run(args.mode, args.report_dir, args.test_receipt))


