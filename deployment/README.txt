ONE.COM SFTP DEPLOYMENT — SCHIER
==============================

Status
------
A push only updates GitHub; it does not publish files to one.com.
The first successful workflow run must be the read-only Test.
The owner explicitly chose TOFU if three separate ED25519 connections agree.
All three agreed on 2026-10-20, so that exact public key is now pinned in known_hosts.
The three observations are recorded in host-key-tofu.json. No independent identity
verification by one.com is claimed. RSA/ECDSA candidates remain untrusted.
Deployment still requires the target variables and a complete read-only Test.

Project and publication scope
-----------------------------
This is a static site: HTML, CSS, JavaScript, images, favicons, Apache .htaccess,
robots.txt, sitemap.xml and a webmanifest. There is no package.json/build tool,
server-side application, database configuration or upload handler in the repository.
No build is required.

deployment/public-files.json lists exactly the 236 current public files.
Only explicitly listed, Git-tracked, regular files can be published. The script
also validates their paths and permitted types. Symlinks and traversal are rejected.
Neither the repository root nor a directory glob is uploaded wholesale.

Git metadata, .github/, deployment/, documentation, tests, requirements, .env files,
desktop.ini, local configuration and anything not listed in the public manifest
are excluded. Existing review/profile pictures and public contact information
remain part of the website.

The server has not been inventoried. It may contain uploads, databases/configuration,
provider-managed files or unrelated files not present locally. Those remain intact.
No SFTP remove, unlink or rmdir command, rsync, SCP or remote shell is used.
Removing a file from Git/the manifest does NOT remove its existing server copy.

Connection and target configuration
-----------------------------------
Existing repository secrets:
  SFTP_HOST      ssh.cmcay2ntn.service.one  (hostname only)
  SFTP_USER      your one.com SFTP username
  SFTP_PASSWORD  your one.com SFTP password
Port is fixed at 22. The password is passed to Paramiko only through the step
environment. It is never written to configuration, logs or a receipt.

Configure these repository Actions VARIABLES under:
Settings -> Secrets and variables -> Actions -> Variables

  SFTP_REMOTE_DIR
    /customers/7/7/4/cmcay2ntn/webroots/www
    This is the path supplied by the site owner. Use no trailing slash.

  SFTP_ROOT_CONFIRMED
    true
    Set only after confirming this is schier.dk's webroot in one.com/SFTP.
    The workflow additionally rejects symlinks/non-directories and checks that
    index.html identifies https://www.schier.dk/. A wrong/missing path fails closed.

No SFTP_HOST_KEY_SHA256 Actions variable is needed. The complete trusted key is
versioned in deployment/known_hosts. Repository variables cannot replace that pin.

If the SFTP path differs from the control panel's full filesystem path, the Test
will report failure rather than deploy elsewhere. With a verified host key but
no SFTP_REMOTE_DIR, Test can show read-only landing-folder/candidate hints.
Discovery is NOT reported as a passing comparison and creates no Test receipt.

Host-key trust — explicit TOFU, then strict pinning
------------------------------------------------
The owner authorized TOFU if three separate connections to the endpoint agreed.
All three scans returned the following complete ED25519 key and fingerprint:

  Endpoint: ssh.cmcay2ntn.service.one:22
  SHA256:iDgAh/1dj9HyXk3nOztS6nK7jJI1IyR2uUrxDCF9kI8
  ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIHqIQzp1R9ZzoL0Mw4ERjRBsiHP10j8LkY8ch8C/vtyt

deployment/known_hosts is the sole full-key trust file.
deployment/host-key-tofu.json records the separate scans and their UTC timestamps.
onecom-host-keys.UNVERIFIED contains historical multi-algorithm candidates and is
NOT loaded; its RSA/ECDSA entries are NOT trusted by this workflow.

TOFU establishes continuity with the first observed key. Three matching scans are
not independent proof of server identity; an attacker on the initial network path
could consistently present the same key. The owner explicitly accepted this model.
There is no runtime keyscan, automatic key acceptance or automatic pin refresh.

After the existing main/receipt guards, each real Test/Deploy first opens a pure
OpenSSH SFTP session using:
  StrictHostKeyChecking=yes
  UserKnownHostsFile=<repository>/deployment/known_hosts
  GlobalKnownHostsFile=/dev/null
  HostKeyAlgorithms=ssh-ed25519
  VerifyHostKeyDNS=no
  UpdateHostKeys=no
The preflight sends only "pwd" and "quit", no remote shell command or file writes.
Password prompting uses an ephemeral ASKPASS helper that references the secret
environment variable. No password is embedded in the helper or written to logs.
OpenSSH output is suppressed, and failure stops the workflow before transfer.

Paramiko then independently checks the same pinned ED25519 fingerprint before
sending its password. Thus a key change between the preflight and comparison is
also rejected. The two SFTP connections require no shell support.
A changed/missing/unrecognized key is an error, never an invitation to auto-accept.
Verify legitimate provider key rotations out of band and deliberately review a
new pin in Git; never overwrite known_hosts with a fresh scan during deployment.

Putting the reviewed workflow on GitHub
--------------------------------------
After reviewing the code and the owner's accepted TOFU pin:

  cd C:\Projekter\Schier\Hjemmeside-github-sync
  git status
  git add .github/workflows/deploy.yml deployment
  git diff --cached --stat
  git commit -m "Add manual verified SFTP deployment to one.com"
  git push origin main

No push-triggered deployment exists. The workflow becomes available when its
definition is committed to main. It can ONLY be dispatched manually from main.
The original C:\Projekter\Schier\Hjemmeside directory is not used or modified.

First run — Test
----------------
1. Open https://github.com/ufst-my/schier/actions
2. Select "one.com SFTP" -> Run workflow -> branch main.
3. Set mode to Test. Leave test_run_id empty.
4. Review the Summary and the downloadable sftp-report artifact.

Test first performs the read-only strict OpenSSH preflight, then SFTP read/stat/list operations. It never creates a remote test
file or directory, chmods, uploads, renames or deletes anything.
For EVERY manifest file, the existing remote content is read and SHA-256 hashed;
equal sizes or timestamps are never taken as proof of equality.
The report labels NEW, CHANGED, UNCHANGED and ERROR. Unreadable, unstable or
symlinked files are errors, not new/unchanged files. An incomplete comparison fails.

A passing Test uploads a small GitHub artifact called sftp-test-receipt.
It records the commit, manifest hash, connection/configuration digest, canonical
root, run ID/attempt and time. It contains no password or server-file contents.
Copy the numeric run ID from the Actions URL: /actions/runs/123456789.

Later run — Deploy
------------------
1. Use the SAME main commit and target configuration as the passing Test.
2. Run "one.com SFTP" manually on main, choose Deploy and enter that Test run ID.
3. The Test must be successful, from this workflow/repository/main, match this
   commit and configuration, and be no more than 24 hours old.
4. The run downloads/validates the Test receipt and re-compares the current server.
5. Only NEW/CHANGED public files are uploaded. UNCHANGED files are not uploaded.
6. Each upload is written to an exclusive temporary file, verified, then renamed.
   Changed live files require the SFTP posix-rename extension for atomic replacement.
   No shell access is needed; there is NO delete-then-rename fallback.
7. Published files are read back and verified. Review Summary for the result.

A Deploy without a valid earlier Test is rejected BEFORE SFTP connects.
Both Test and Deploy share a fixed concurrency group, so they cannot overlap.
A run whose commit is no longer the tip of main is rejected to prevent stale deploys.

Daily changes
-------------
Make all edits in Hjemmeside-github-sync, commit and push to main, then run Test
and Deploy for that commit. Merely pushing does not publish to one.com.

When adding a NEW public file, also add its exact relative path to
deployment/public-files.json in the same commit. Otherwise it is deliberately
not published. New service pages fit ydelser/<service>/index.html. If a new public
file type/location is necessary, review allowed_public_path in sftp_deploy.py.
Never add credentials or server-owned files to the manifest.

Deletions must be planned separately. Stale images, old icon folders and removed
pages remain on one.com until an explicitly reviewed manual cleanup.

Operational limits and remaining checks
---------------------------------------
- Local safety tests alone do not establish server contents or access. Only a
  successful read-only Actions Test can establish the current comparison.
- The owner supplied the target path; its SFTP visibility and site identity still
  need verification by the first real Test with the TOFU-pinned key.
- The remote account must allow reading managed files for a genuine comparison.
  A write-only account cannot safely satisfy this workflow and is rejected.
- Support for atomic posix-rename cannot be established by a strictly read-only
  Test. An unsupported replacement fails without truncating/deleting the target.
- A failed/interrupted Deploy can be partial; this is not an atomic whole-site
  release. Assets precede HTML; .htaccess is last. Check the per-file upload state.
- Interrupted uploads can leave hidden .sftp-deploy-<random>.tmp files. This
  workflow never deletes them automatically. Inspect/remove manually if needed.
- Avoid concurrent edits through SFTP/File Manager while deploying. The workflow
  rechecks targets but cannot lock out other clients.
- Keep a one.com backup before the first Deploy. Git only backs up tracked code,
  not unknown server-only files. Restoring an older Git version requires a new
  main commit (e.g. a revert), a new Test, and Deploy; no force-push is needed.
- Reports list public file paths/hashes and unmanaged top-level names, not server
  file contents. No server banners/raw connection exceptions are logged.
- File limits: 32 MiB per managed file, 256 MiB local publication, 2000 manifest
  entries. Reads have network timeouts and the Actions job has a 25 minute limit.
- Official GitHub actions are pinned to full commit SHAs. Python is pinned to
  3.13.16; Paramiko and every transitive runtime package have exact versions and
  PyPI wheel hashes. Update/review these pins together as security fixes arrive.
  Ubuntu runner system packages remain maintained by GitHub's runner image.

Local verification performed
----------------------------
Safety tests include a real loopback-only SSH/SFTP server with NO shell:
  python -m unittest discover -s deployment/tests -v
Tests cover read-only comparison, equal-size changes, host-key rejection before
authentication, no-previous-Test rejection, non-main rejection, unsafe paths,
unreadable files, symlinks, remote-only preservation, concurrent remote changes,
atomic uploads, unsupported rename, and receipt expiry/commit/configuration.
These tests never connect to one.com.
Linux CPython 3.13 dependency wheels were resolved and checked against the lock.
The full GitHub Actions run itself can only be validated after the reviewed
workflow is committed/pushed and a manual Test is dispatched.

Official references
-------------------
https://man.openbsd.org/ssh_config#StrictHostKeyChecking
https://man.openbsd.org/sftp
https://docs.paramiko.org/en/stable/api/client.html
https://docs.paramiko.org/en/stable/api/sftp.html
https://docs.github.com/en/actions/how-tos/manage-workflow-runs/manually-run-a-workflow
https://help.one.com/hc/en-us/articles/49226612219153-Where-can-I-find-the-File-System-Path-for-my-domain-or-subdomain



Preview target: test.schier.dk
----------------------------
Choose target Preview (the default) for the separate test website.
Production still uses its existing SFTP_REMOTE_DIR / SFTP_ROOT_CONFIRMED variables.
Preview uses SFTP_PREVIEW_REMOTE_DIR and SFTP_PREVIEW_ROOT_CONFIRMED=true.
The owner confirmed /webroots/df12bd7c in the one.com control panel.
Its sole allowed canonical SFTP root is:
  /customers/7/7/4/cmcay2ntn/webroots/df12bd7c
The workflow verifies this exact directory and rejects symlinks, a missing root,
production fallback or a different canonical root. It never creates a webroot.
An empty Preview root or a provider default index is permitted for first upload.

Preview publishes the same 236-file manifest, with two deterministic overlays:
- .htaccess from deployment/preview.htaccess: test host only, HTTPS redirect to
  test.schier.dk, X-Robots-Tag noindex/nofollow/noarchive, index.html as default.
- robots.txt: User-agent: * / Disallow: /.
These overrides do not change the production website files in Git.
Production canonical/SEO URLs in HTML stay unchanged.
Noindex is a request to search engines, not password protection.
The Preview .htaccess is published first, before public pages.

First run Preview + Test, then Preview + Deploy with that successful run ID.
Receipts are bound to target, root, commit, overlay bytes and full manifest;
a Production Test cannot authorize a Preview Deploy, or the reverse.
The shared concurrency group serializes both targets. Existing secrets and
the pinned TOFU ED25519 host key / StrictHostKeyChecking=yes are unchanged.
No deletion was added. The owner removed hohoho and visit in the control panel.

The job permits 60 minutes for initial full uploads and per-file verification.

Indexing policy (supersedes the earlier robots.txt overlay description)
---------------------------------------------------------------------
Source HTML and Preview HTML use noindex. robots.txt allows crawling so crawlers
can read the noindex rule; robots.txt itself cannot reliably prevent indexing.
Preview also sends X-Robots-Tag: noindex, nofollow, noarchive.
Production always receives deployment/production-robots.txt as public robots.txt
(Allow: /, empty Disallow, production sitemap), regardless of source robots.txt.
Production HTML is transformed to index,follow,max-image-preview:large; the 404
page remains noindex. Production publication fails if the robots template differs
from the exact allow policy, if a page lacks the expected robots meta, or if the
production .htaccess contains noindex. Test receipts hash these final bytes.
Only Preview was authorized for publication in this task. Production is untouched.

Navigation fixes: desktop first activation keeps a hover/focus-opened submenu open;
a second activation closes it. Mobile toggles are at least 44x44 CSS pixels.
The mobile menu scrolls within the available screen height. Long headings wrap.
All Contact calls lead to kontakt/#contact-overview-title; normal skip links,
review placeholders and obfuscated email links are unchanged.
