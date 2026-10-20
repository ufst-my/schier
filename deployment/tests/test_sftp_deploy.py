"""Offline safety tests and loopback SFTP integration; never connect to one.com."""
from __future__ import annotations
import base64
import copy
from datetime import datetime, timedelta, timezone
import errno
import hashlib
import io
import json
import os
from pathlib import Path
import socket
import stat
import sys
import tempfile
import threading
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import paramiko
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import sftp_deploy as deploy


def public(path, data):
    return deploy.PublicFile(path, data, hashlib.sha256(data).hexdigest())


class MemorySFTP:
    def __init__(self, files=None):
        self.files = dict(files or {})
        self.dirs = {"/", "/site"}
        self.links = set()
        self.denied = set()
        self.writes = []
        self.atomic_supported = True

    def lstat(self, path):
        if path in self.denied:
            raise PermissionError(errno.EACCES, "read denied")
        if path in self.links:
            return SimpleNamespace(st_mode=stat.S_IFLNK | 0o777, st_size=1, st_mtime=1)
        if path in self.dirs:
            return SimpleNamespace(st_mode=stat.S_IFDIR | 0o755, st_size=0, st_mtime=1)
        if path in self.files:
            return SimpleNamespace(st_mode=stat.S_IFREG | 0o644,
                                   st_size=len(self.files[path]), st_mtime=1)
        raise FileNotFoundError(errno.ENOENT, "missing")

    def open(self, path, mode):
        if mode == "rb":
            if path in self.denied:
                raise PermissionError(errno.EACCES, "read denied")
            return io.BytesIO(self.files[path])
        if mode != "wx":
            raise AssertionError("Only exclusive temporary writes are allowed")
        if path in self.files:
            raise FileExistsError(errno.EEXIST, "exists")
        self.writes.append(("temporary", path))
        owner = self
        class Writer(io.BytesIO):
            def close(handle):
                if not handle.closed:
                    owner.files[path] = handle.getvalue()
                super().close()
        return Writer()

    def mkdir(self, path, mode=0o755):
        self.writes.append(("mkdir", path))
        self.dirs.add(path)

    def chmod(self, path, mode):
        self.writes.append(("chmod", path))

    def rename(self, source, target):
        if target in self.files:
            raise FileExistsError(errno.EEXIST, "exists")
        self.writes.append(("rename", target))
        self.files[target] = self.files.pop(source)

    def posix_rename(self, source, target):
        if not self.atomic_supported:
            raise OSError("atomic rename unsupported")
        self.writes.append(("posix_rename", target))
        self.files[target] = self.files.pop(source)


class SafetyTests(unittest.TestCase):
    def test_equal_length_changes_are_hashed_and_test_does_not_write(self):
        remote = MemorySFTP({"/site/a.css": b"AAAA", "/site/b.css": b"same"})
        before = copy.deepcopy(remote.files)
        rows = deploy.compare_files(remote, "/site", [
            public("a.css", b"BBBB"), public("b.css", b"same"), public("new.css", b"new")
        ])
        self.assertEqual([r["status"] for r in rows], ["CHANGED", "UNCHANGED", "NEW"])
        self.assertEqual(remote.writes, [])
        self.assertEqual(remote.files, before)

    def test_unreadable_files_are_errors_not_new_files(self):
        remote = MemorySFTP({"/site/a.css": b"data"})
        remote.denied.add("/site/a.css")
        rows = deploy.compare_files(remote, "/site", [public("a.css", b"new")])
        self.assertEqual(rows[0]["status"], "ERROR")
        with self.assertRaises(deploy.SafeError):
            deploy.deploy_files(remote, "/site", [public("a.css", b"new")], rows)
        self.assertEqual(remote.writes, [])

    def test_symlinks_and_symlink_ancestors_block_publication(self):
        remote = MemorySFTP()
        remote.links.add("/site/images")
        rows = deploy.compare_files(remote, "/site", [public("images/a.jpg", b"x")])
        self.assertEqual(rows[0]["status"], "ERROR")
        self.assertEqual(remote.writes, [])

    def test_remote_only_files_are_preserved_and_uploads_are_verified(self):
        remote = MemorySFTP({"/site/index.html": b"old", "/site/server.php": b"keep",
                             "/site/unchanged.css": b"same"})
        files = [public("index.html", b"new"), public("images/new.jpg", b"photo"),
                 public("unchanged.css", b"same")]
        rows = deploy.compare_files(remote, "/site", files)
        deploy.deploy_files(remote, "/site", files, rows)
        self.assertEqual(remote.files["/site/server.php"], b"keep")
        self.assertEqual(remote.files["/site/index.html"], b"new")
        self.assertEqual(remote.files["/site/images/new.jpg"], b"photo")
        self.assertEqual([r.get("upload_state") for r in rows], ["VERIFIED", "VERIFIED", None])
        renames = [path for op, path in remote.writes if op in {"rename", "posix_rename"}]
        self.assertEqual(renames, ["/site/images/new.jpg", "/site/index.html"])

    def test_unsupported_atomic_rename_keeps_old_target(self):
        remote = MemorySFTP({"/site/index.html": b"old"})
        remote.atomic_supported = False
        files = [public("index.html", b"new")]
        rows = deploy.compare_files(remote, "/site", files)
        with self.assertRaises(OSError):
            deploy.deploy_files(remote, "/site", files, rows)
        self.assertEqual(remote.files["/site/index.html"], b"old")
        self.assertFalse(any(op == "remove" for op, _ in remote.writes))

    def test_server_change_after_comparison_blocks_overwrite(self):
        remote = MemorySFTP({"/site/index.html": b"old"})
        files = [public("index.html", b"new")]
        rows = deploy.compare_files(remote, "/site", files)
        remote.files["/site/index.html"] = b"edited-on-server"
        with self.assertRaises(deploy.SafeError):
            deploy.deploy_files(remote, "/site", files, rows)
        self.assertEqual(remote.writes, [])

    def test_allowlist_rejects_metadata_secrets_code_and_traversal(self):
        for name in [".git/config", ".github/workflows/deploy.yml", ".env", "README.md",
                     "icons/favicon-32x32.png",
                     "deployment/sftp_deploy.py", "images/.env", "images/desktop.ini",
                     "images/../private.jpg", "/index.html", "uploads/file.jpg",
                     "kontakt/config.php", "images/backups/file.jpg", "js/new.js\n::error::x"]:
            with self.subTest(name=name):
                self.assertFalse(deploy.allowed_public_path(name))
        for name in [".htaccess", "kontakt/.htaccess", "index.html", "js/script.js",
                     "images/cards/a.avif", "images/icons/favicon-32x32.png", "ydelser/trappevask/index.html"]:
            self.assertTrue(deploy.allowed_public_path(name))

    def test_manifest_matches_exact_tracked_public_files(self):
        files = deploy.load_public_files()
        self.assertTrue({"index.html", ".htaccess", "css/style.css", "js/script.js"}.issubset(
            {file.path for file in files}))
        self.assertFalse(any(f.path.startswith(("deployment/", ".github/")) for f in files))

    def test_config_rejects_unverified_key_and_unsafe_root(self):
        env = {"SFTP_HOST": "example.test", "SFTP_USER": "local-test",
               "SFTP_PASSWORD": "local-test-only", "SFTP_HOST_KEY_SHA256": ""}
        with patch.dict(os.environ, env, clear=True):
            with self.assertRaises(deploy.SafeError):
                deploy.load_config()
        env["SFTP_HOST_KEY_SHA256"] = "SHA256:" + "A" * 43
        env["SFTP_REMOTE_DIR"] = "/site/../other"
        with patch.dict(os.environ, env, clear=True):
            with self.assertRaises(deploy.SafeError):
                deploy.load_config()

    def test_root_identity_must_match_schier(self):
        remote = MemorySFTP({"/site/index.html": b"another website"})
        remote.normalize = lambda path: path
        with self.assertRaises(deploy.SafeError):
            deploy.validate_root(remote, "/site")

    def test_deploy_requires_same_successful_recent_test_and_config(self):
        env = {"GITHUB_REPOSITORY": "ufst-my/schier", "GITHUB_SHA": "a" * 40,
               "GITHUB_RUN_ID": "123", "GITHUB_RUN_ATTEMPT": "1"}
        config = deploy.Config("example.test", "local-test", "local-test-only",
                               "SHA256:" + "A" * 43, "/site", True)
        files = [public("index.html", b"site")]
        with patch.dict(os.environ, env):
            receipt = deploy.make_receipt(config, files, "/site")
            metadata = {"id": 123, "run_attempt": 1, "status": "completed",
                        "conclusion": "success", "event": "workflow_dispatch",
                        "head_branch": "main", "head_sha": env["GITHUB_SHA"],
                        "path": ".github/workflows/deploy.yml",
                        "head_repository": {"full_name": "ufst-my/schier"}}
            deploy.validate_receipt(receipt, config, files, "123", metadata)
            for field, value in [("conclusion", "failure"), ("head_branch", "other"),
                                 ("event", "push"), ("head_sha", "b" * 40),
                                 ("path", ".github/workflows/other.yml"), ("run_attempt", 2)]:
                changed = dict(metadata, **{field: value})
                with self.subTest(field=field), self.assertRaises(deploy.SafeError):
                    deploy.validate_receipt(receipt, config, files, "123", changed)
            with self.assertRaises(deploy.SafeError):
                deploy.validate_receipt(receipt, config, [public("index.html", b"changed")],
                                        "123", metadata)
            changed_config = deploy.Config("other.test", "local-test", "local-test-only",
                                           config.fingerprint, "/site", True)
            with self.assertRaises(deploy.SafeError):
                deploy.validate_receipt(receipt, changed_config, files, "123", metadata)
            with self.assertRaises(deploy.SafeError):
                deploy.validate_receipt(receipt, config, files, "123", metadata,
                                        datetime.now(timezone.utc) + timedelta(hours=25))

    def test_early_failure_report_does_not_claim_comparison(self):
        with tempfile.TemporaryDirectory() as folder, patch.dict(os.environ, {}, clear=True):
            with patch.object(deploy, "load_config", side_effect=deploy.SafeError("Key not verified.")):
                result = deploy.run("Test", Path(folder), Path(folder) / "missing.json")
            report = json.loads((Path(folder) / "report.json").read_text())
            self.assertEqual(result, 1)
            self.assertEqual(report["result"], "FAILED")
            self.assertEqual(report["files"], [])
            self.assertFalse((Path(folder) / "test-receipt.json").exists())


    def test_deploy_without_prior_test_never_connects(self):
        env = {"GITHUB_RUN_ID": "123", "SFTP_TEST_RUN_ID": ""}
        config = deploy.Config("example.test", "local-test", "local-test-only",
                               "SHA256:" + "A" * 43, "/site", True)
        with tempfile.TemporaryDirectory() as folder, patch.dict(os.environ, env):
            with patch.object(deploy, "load_config", return_value=config), \
                 patch.object(deploy, "assert_current_main"), \
                 patch.object(deploy, "connect") as connection:
                result = deploy.run("Deploy", Path(folder), Path(folder) / "missing.json")
            connection.assert_not_called()
            self.assertEqual(result, 1)
            self.assertFalse((Path(folder) / "test-receipt.json").exists())

    def test_non_main_run_is_rejected(self):
        env = {"GITHUB_ACTIONS": "true", "GITHUB_EVENT_NAME": "workflow_dispatch",
               "GITHUB_REF": "refs/heads/other"}
        with patch.dict(os.environ, env):
            with patch.object(deploy, "github_json") as api:
                with self.assertRaises(deploy.SafeError):
                    deploy.assert_current_main()
                api.assert_not_called()

    def test_repository_pin_is_the_three_times_observed_ed25519_key(self):
        host, fingerprint = deploy.pinned_identity()
        self.assertEqual(host, "ssh.cmcay2ntn.service.one")
        self.assertEqual(fingerprint, "SHA256:iDgAh/1dj9HyXk3nOztS6nK7jJI1IyR2uUrxDCF9kI8")

    def test_environment_cannot_override_the_pinned_key(self):
        env = {"SFTP_HOST": "ssh.cmcay2ntn.service.one", "SFTP_USER": "local-test",
               "SFTP_PASSWORD": "local-test-only", "SFTP_HOST_KEY_SHA256": "SHA256:" + "A" * 43}
        with patch.dict(os.environ, env, clear=True), self.assertRaises(deploy.SafeError):
            deploy.load_config()

    def test_pinned_config_needs_no_fingerprint_variable(self):
        env = {"SFTP_HOST": "ssh.cmcay2ntn.service.one", "SFTP_USER": "local-test",
               "SFTP_PASSWORD": "local-test-only", "SFTP_REMOTE_DIR": "/site"}
        with patch.dict(os.environ, env, clear=True):
            config = deploy.load_config()
            self.assertEqual(config.fingerprint,
                             "SHA256:iDgAh/1dj9HyXk3nOztS6nK7jJI1IyR2uUrxDCF9kI8")

    def test_strict_openssh_preflight_sends_only_read_only_commands(self):
        config = deploy.Config("ssh.cmcay2ntn.service.one", "local-test", "local-test-only",
                               "SHA256:" + "A" * 43, "/site", True)
        run_real = deploy.subprocess.run
        helpers = []
        def simulate_sftp(*args, **kwargs):
            helper = Path(kwargs["env"]["SSH_ASKPASS"])
            helpers.append(helper)
            helper_source = helper.read_text(encoding="utf-8")
            self.assertNotIn(config.password, helper_source)
            compile(helper_source, str(helper), "exec")
            answer = run_real([sys.executable, str(helper)], env=kwargs["env"],
                              capture_output=True, text=True, check=True)
            self.assertEqual(answer.stdout, config.password + "\n")
            return SimpleNamespace(returncode=0)
        with patch.object(deploy.sys, "platform", "linux"), \
             patch.object(deploy.subprocess, "run", side_effect=simulate_sftp) as process:
            deploy.openssh_preflight(config)
            args, kwargs = process.call_args
            command = args[0]
            self.assertIn("-oStrictHostKeyChecking=yes", command)
            self.assertIn("-oHostKeyAlgorithms=ssh-ed25519", command)
            self.assertIn("-oUpdateHostKeys=no", command)
            self.assertIn("-oGlobalKnownHostsFile=/dev/null", command)
            self.assertIn("-oUserKnownHostsFile=" + str(deploy.KNOWN_HOSTS), command)
            self.assertNotIn(config.password, command)
            self.assertEqual(kwargs["input"], "pwd\nquit\n")
            self.assertEqual(kwargs["stdout"], deploy.subprocess.DEVNULL)
            self.assertEqual(kwargs["stderr"], deploy.subprocess.DEVNULL)
            self.assertEqual(kwargs["env"]["SSH_ASKPASS_REQUIRE"], "force")
            self.assertTrue(helpers)
            self.assertFalse(helpers[0].exists())

    def test_openssh_rejection_blocks_paramiko_and_upload(self):
        config = deploy.Config("ssh.cmcay2ntn.service.one", "local-test", "local-test-only",
                               "SHA256:" + "A" * 43, "/site", True)
        with tempfile.TemporaryDirectory() as folder:
            with patch.object(deploy, "load_config", return_value=config), \
                 patch.object(deploy, "assert_current_main"), \
                 patch.object(deploy.sys, "platform", "linux"), \
                 patch.object(deploy.subprocess, "run", return_value=SimpleNamespace(returncode=255)), \
                 patch.object(deploy, "load_public_files", return_value=[public("index.html", b'<meta name="robots" content="noindex,nofollow" />site')]), \
                 patch.object(deploy, "connect") as connection:
                code = deploy.run("Test", Path(folder), Path(folder) / "missing.json")
            self.assertEqual(code, 1)
            connection.assert_not_called()
            self.assertFalse((Path(folder) / "test-receipt.json").exists())


class PreviewSafetyTests(unittest.TestCase):
    def config(self, root=None, confirmed=True):
        return deploy.Config("ssh.cmcay2ntn.service.one", "local-test", "local-test-only",
                             deploy.pinned_identity()[1], root or deploy.PREVIEW_ROOT,
                             confirmed, target="Preview")

    def remote(self):
        remote = MemorySFTP()
        from pathlib import PurePosixPath
        for path in (deploy.PREVIEW_ROOT, deploy.PREVIEW_ALIAS):
            remote.dirs.update(str(p) for p in [PurePosixPath(path), *PurePosixPath(path).parents])
        remote.normalize = lambda path: deploy.PREVIEW_ROOT
        remote.listdir_iter = lambda *args, **kwargs: iter([])
        remote.close = lambda: None
        return remote

    def test_preview_config_has_no_production_fallback(self):
        env = {"SFTP_HOST": "ssh.cmcay2ntn.service.one", "SFTP_USER": "local-test",
               "SFTP_PASSWORD": "local-test-only", "SFTP_TARGET": "Preview",
               "SFTP_REMOTE_DIR": deploy.PRODUCTION_ROOT, "SFTP_ROOT_CONFIRMED": "true"}
        with patch.dict(os.environ, env, clear=True), self.assertRaises(deploy.SafeError):
            deploy.load_config()
        env.update(SFTP_PREVIEW_REMOTE_DIR=deploy.PREVIEW_ALIAS,
                   SFTP_PREVIEW_ROOT_CONFIRMED="true")
        with patch.dict(os.environ, env, clear=True):
            config = deploy.load_config()
            self.assertEqual(config.target, "Preview")
            self.assertEqual(config.remote_dir, deploy.PREVIEW_ALIAS)
            self.assertTrue(config.root_confirmed)
        env["SFTP_PREVIEW_REMOTE_DIR"] = deploy.PRODUCTION_ROOT
        with patch.dict(os.environ, env, clear=True), self.assertRaises(deploy.SafeError):
            deploy.load_config()

    def test_empty_confirmed_preview_root_is_allowed_without_writes(self):
        remote = self.remote()
        for path in [deploy.PREVIEW_ROOT, deploy.PREVIEW_ALIAS]:
            self.assertEqual(deploy.validate_target_root(remote, self.config(path)), deploy.PREVIEW_ROOT)
        self.assertEqual(remote.writes, [])

    def test_wrong_canonical_root_and_production_are_rejected(self):
        for path in [deploy.PRODUCTION_ROOT, "/", "/webroots/elsewhere"]:
            remote = self.remote()
            remote.normalize = lambda _: path
            with self.assertRaises(deploy.SafeError):
                deploy.validate_target_root(remote, self.config())
            self.assertEqual(remote.writes, [])
        with self.assertRaises(deploy.SafeError):
            deploy.validate_target_root(self.remote(), self.config(deploy.PRODUCTION_ROOT))

    def test_missing_unconfirmed_or_symlink_root_is_rejected(self):
        remote = self.remote()
        remote.dirs.remove(deploy.PREVIEW_ROOT)
        with self.assertRaises(deploy.SafeError):
            deploy.validate_target_root(remote, self.config())
        with self.assertRaises(deploy.SafeError):
            deploy.validate_target_root(self.remote(), self.config(confirmed=False))
        remote = self.remote()
        remote.links.add(deploy.PREVIEW_ROOT)
        with self.assertRaises(deploy.SafeError):
            deploy.validate_target_root(remote, self.config())
        self.assertEqual(remote.writes, [])

    def test_production_still_requires_schier_index(self):
        remote = self.remote()
        remote.normalize = lambda path: path
        config = deploy.Config("example.test", "local-test", "local-test-only", "pin", "/site", True)
        with self.assertRaises(deploy.SafeError):
            deploy.validate_target_root(remote, config)

    def test_overlays_do_not_change_production_sources(self):
        files = [public(".htaccess", b"production redirect"),
                 public("robots.txt", b"User-agent: *\nDisallow: /\n"),
                 public("index.html", b'<meta name="robots" content="noindex,nofollow" />site')]
        production = deploy.Config("example.test", "local-test", "local-test-only", "pin", "/site", True)
        prod = {f.path: f.content for f in deploy.publication_files(files, production)}
        self.assertIn(b"Allow: /", prod["robots.txt"])
        self.assertNotIn(b"Disallow: /", prod["robots.txt"])
        self.assertIn(b"index,follow,max-image-preview:large", prod["index.html"])
        self.assertNotIn(b"noindex", prod["index.html"])
        self.assertIn(b"noindex", files[2].content)
        result = deploy.publication_files(files, self.config())
        self.assertEqual(len(files), len(result))
        self.assertEqual(files[0].content, b"production redirect")
        self.assertEqual(result[2], files[2])
        self.assertIn(b"https://test.schier.dk", result[0].content)
        self.assertNotIn(b"www.schier.dk", result[0].content)
        self.assertIn(b"noindex, nofollow, noarchive", result[0].content)
        self.assertNotIn(b"Disallow: /", result[1].content)
        self.assertIn(b"noindex", result[2].content)
        self.assertNotEqual(deploy.manifest_digest(result), deploy.manifest_digest(files))

    def test_production_policy_cannot_be_overridden_by_source_robots(self):
        files = deploy.load_public_files()
        production = deploy.Config("example.test", "local-test", "local-test-only", "pin", "/site", True)
        result = {f.path: f.content for f in deploy.publication_files(files, production)}
        self.assertIn(b"Allow: /", result["robots.txt"])
        self.assertNotIn(b"Disallow: /", result["robots.txt"])
        for path, content in result.items():
            if path.endswith(".html") and path != "404.html":
                self.assertIn(b'content="index,follow,max-image-preview:large"', content)
                self.assertNotIn(b'content="noindex', content)
        self.assertIn(b'content="noindex', result["404.html"])
        self.assertNotIn(b"noindex", result[".htaccess"])
        preview = {f.path: f.content for f in deploy.publication_files(files, self.config())}
        for path, content in preview.items():
            if path.endswith(".html"):
                self.assertIn(b'content="noindex', content)

    def test_invalid_production_policy_blocks_before_publication(self):
        production = deploy.Config("example.test", "local-test", "local-test-only", "pin", "/site", True)
        source = public("index.html", b'<meta name="robots" content="noindex,nofollow" />')
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / "deployment").mkdir()
            (root / "deployment" / "production-robots.txt").write_bytes(b"User-agent: *\nDisallow: /\n")
            with patch.object(deploy, "REPO", root), self.assertRaises(deploy.SafeError):
                deploy.publication_files([source], production)
        with self.assertRaises(deploy.SafeError):
            deploy.publication_files([public("index.html", b"missing robots meta")], production)
        with self.assertRaises(deploy.SafeError):
            deploy.publication_files([source, public(".htaccess", b"Header set X-Robots-Tag noindex")], production)

    def test_receipt_digest_separates_targets_even_for_same_files(self):
        from dataclasses import replace
        preview = self.config()
        production = replace(preview, target="Production")
        files = [public("index.html", b"site")]
        self.assertNotEqual(deploy.configuration_digest(preview, files),
                            deploy.configuration_digest(production, files))

    def test_preview_host_guards_are_published_before_pages(self):
        remote = MemorySFTP()
        files = [public("index.html", b"site"), public(".htaccess", b"guard"),
                 public("robots.txt", b"deny")]
        rows = deploy.compare_files(remote, "/site", files)
        deploy.deploy_files(remote, "/site", files, rows, preview=True)
        targets = [path for op, path in remote.writes if op == "rename"]
        self.assertEqual(targets[0], "/site/.htaccess")
        self.assertTrue(all(r["upload_state"] == "VERIFIED" for r in rows))

    def test_full_preview_test_reads_only_and_records_exact_root(self):
        remote = self.remote()
        files = [public(".htaccess", b"production"), public("robots.txt", b"allow"),
                 public("index.html", b"site")]
        env = {"GITHUB_REPOSITORY": "ufst-my/schier", "GITHUB_SHA": "a" * 40,
               "GITHUB_RUN_ID": "123", "GITHUB_RUN_ATTEMPT": "1"}
        with tempfile.TemporaryDirectory() as folder, patch.dict(os.environ, env):
            with patch.object(deploy, "load_public_files", return_value=files), \
                 patch.object(deploy, "load_config", return_value=self.config()), \
                 patch.object(deploy, "assert_current_main"), \
                 patch.object(deploy, "openssh_preflight"), \
                 patch.object(deploy, "connect", return_value=(SimpleNamespace(close=lambda: None), remote)):
                result = deploy.run("Test", Path(folder), Path(folder) / "missing.json")
            report = json.loads((Path(folder) / "report.json").read_text())
            receipt = json.loads((Path(folder) / "test-receipt.json").read_text())
            self.assertEqual(result, 0)
            self.assertEqual(report["target"], "Preview")
            self.assertEqual(report["canonical_root"], deploy.PREVIEW_ROOT)
            self.assertEqual(receipt["remote_writes"], 0)
            self.assertEqual(receipt["canonical_root"], deploy.PREVIEW_ROOT)
            self.assertTrue(all(row["status"] == "NEW" for row in report["files"]))
            self.assertEqual(remote.writes, [])


# A real SSH/SFTP server bound ONLY to loopback. It exposes no shell at all.
class LoopbackServer(paramiko.ServerInterface):
    def __init__(self):
        self.auth_attempts = 0

    def check_auth_password(self, username, password):
        self.auth_attempts += 1
        return paramiko.AUTH_SUCCESSFUL

    def get_allowed_auths(self, username):
        return "password"

    def check_channel_request(self, kind, chanid):
        return paramiko.OPEN_SUCCEEDED if kind == "session" else paramiko.OPEN_FAILED_ADMINISTRATIVELY_PROHIBITED


class LoopbackFS(paramiko.SFTPServerInterface):
    def __init__(self, server, *args, root, writes, **kwargs):
        super().__init__(server, *args, **kwargs)
        self.root, self.writes = Path(root), writes

    def local(self, path):
        relative = Path(path.lstrip("/"))
        resolved = (self.root / relative).resolve()
        if not resolved.is_relative_to(self.root.resolve()):
            raise PermissionError(errno.EACCES, "outside root")
        return resolved

    def canonicalize(self, path):
        return "/" if path == "." else "/" + path.strip("/")

    def lstat(self, path):
        try:
            return paramiko.SFTPAttributes.from_stat(self.local(path).lstat())
        except OSError as exc:
            return paramiko.SFTPServer.convert_errno(exc.errno)

    stat = lstat

    def list_folder(self, path):
        try:
            result = []
            for child in self.local(path).iterdir():
                info = paramiko.SFTPAttributes.from_stat(child.lstat())
                info.filename = child.name
                result.append(info)
            return result
        except OSError as exc:
            return paramiko.SFTPServer.convert_errno(exc.errno)

    def open(self, path, flags, attr):
        try:
            writing = bool(flags & (os.O_WRONLY | os.O_RDWR))
            if writing:
                self.writes.append(("open", path))
            fd = os.open(self.local(path), flags | getattr(os, "O_BINARY", 0), 0o644)
            stream = os.fdopen(fd, "wb" if writing else "rb")
            handle = paramiko.SFTPHandle(flags)
            if writing:
                handle.writefile = stream
            else:
                handle.readfile = stream
            return handle
        except OSError as exc:
            return paramiko.SFTPServer.convert_errno(exc.errno)

    def mkdir(self, path, attr):
        try:
            self.writes.append(("mkdir", path))
            self.local(path).mkdir()
            return paramiko.SFTP_OK
        except OSError as exc:
            return paramiko.SFTPServer.convert_errno(exc.errno)

    def chattr(self, path, attr):
        self.writes.append(("chmod", path))
        return paramiko.SFTP_OK

    def rename(self, oldpath, newpath):
        try:
            self.writes.append(("rename", newpath))
            if self.local(newpath).exists():
                return paramiko.SFTP_FAILURE
            self.local(oldpath).rename(self.local(newpath))
            return paramiko.SFTP_OK
        except OSError as exc:
            return paramiko.SFTPServer.convert_errno(exc.errno)

    def posix_rename(self, oldpath, newpath):
        try:
            self.writes.append(("posix_rename", newpath))
            os.replace(self.local(oldpath), self.local(newpath))
            return paramiko.SFTP_OK
        except OSError as exc:
            return paramiko.SFTPServer.convert_errno(exc.errno)


class IntegrationTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.root = Path(self.folder.name)
        (self.root / "site").mkdir()
        (self.root / "site/index.html").write_bytes(b"https://www.schier.dk/ old")
        self.files = [public("index.html", b'<meta name="robots" content="noindex,nofollow" />https://www.schier.dk/ new'),
                      public("css/style.css", b"body{}")]
        self.key = paramiko.RSAKey.generate(2048)
        self.fingerprint = "SHA256:" + base64.b64encode(
            hashlib.sha256(self.key.asbytes()).digest()).decode().rstrip("=")
        self.socket = socket.socket()
        self.socket.bind(("127.0.0.1", 0))
        self.socket.listen(1)
        self.socket.settimeout(5)
        self.server = LoopbackServer()
        self.writes = []
        self.transport = None

        def serve():
            try:
                connection, _ = self.socket.accept()
                self.transport = paramiko.Transport(connection)
                self.transport.add_server_key(self.key)
                self.transport.set_subsystem_handler(
                    "sftp", paramiko.SFTPServer, LoopbackFS,
                    root=self.root, writes=self.writes)
                self.transport.start_server(server=self.server)
                # Keep the transport alive until the client closes it.
                self.transport.join(10)
            except (EOFError, OSError, paramiko.SSHException):
                pass
        self.thread = threading.Thread(target=serve, daemon=True)
        self.thread.start()
        self.config = deploy.Config("127.0.0.1", "local-test", "local-test-only",
                                    self.fingerprint, "/site", True,
                                    port=self.socket.getsockname()[1])

    def tearDown(self):
        if self.transport:
            self.transport.close()
        self.socket.close()
        self.thread.join(3)
        self.folder.cleanup()

    def test_real_read_only_sftp_and_complete_receipt(self):
        env = {"GITHUB_REPOSITORY": "ufst-my/schier", "GITHUB_SHA": "a" * 40,
               "GITHUB_RUN_ID": "123", "GITHUB_RUN_ATTEMPT": "1"}
        with tempfile.TemporaryDirectory() as report_dir, patch.dict(os.environ, env):
            with patch.object(deploy, "load_public_files", return_value=self.files), \
                 patch.object(deploy, "load_config", return_value=self.config), \
                 patch.object(deploy, "assert_current_main"), \
                 patch.object(deploy, "openssh_preflight"):
                code = deploy.run("Test", Path(report_dir), Path(report_dir) / "missing.json")
            self.assertEqual(code, 0)
            receipt = json.loads((Path(report_dir) / "test-receipt.json").read_text())
            self.assertEqual(receipt["remote_writes"], 0)
        self.assertEqual(self.writes, [])
        self.assertEqual((self.root / "site/index.html").read_bytes(),
                         b"https://www.schier.dk/ old")
        self.assertFalse((self.root / "site/css").exists())

    def test_real_deploy_uses_only_sftp_and_atomic_rename(self):
        client, sftp = deploy.connect(self.config)
        try:
            root = deploy.validate_root(sftp, self.config.remote_dir)
            rows = deploy.compare_files(sftp, root, self.files)
            deploy.deploy_files(sftp, root, self.files, rows)
            self.assertTrue(all(row["upload_state"] == "VERIFIED" for row in rows))
        finally:
            sftp.close()
            client.close()
        self.assertEqual((self.root / "site/index.html").read_bytes(), self.files[0].content)
        self.assertEqual((self.root / "site/css/style.css").read_bytes(), b"body{}")
        self.assertTrue(any(op == "posix_rename" for op, _ in self.writes))

    def test_wrong_host_key_rejected_before_password_authentication(self):
        config = deploy.Config(self.config.host, self.config.user, self.config.password,
                               "SHA256:" + "A" * 43, "/site", True, self.config.port)
        with self.assertRaises(deploy.SafeError):
            deploy.connect(config)
        self.assertEqual(self.server.auth_attempts, 0)
        self.assertEqual(self.writes, [])


if __name__ == "__main__":
    unittest.main()


