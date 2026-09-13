"""Fetch every file of the Mendeley dataset doi:10.17632/btchxktzyw.

Reads dataset_manifest.json, downloads each file into data_raw/version-<N>/,
and verifies it against the SHA-256 recorded in the manifest. Files that are
already present and verify correctly are skipped, so the script is resumable.

Note on the User-Agent: data.mendeley.com sits behind Cloudflare, which answers
403 to the default urllib agent string. Any ordinary browser-like agent works.
"""
import hashlib
import json
import os
import sys
import time
import urllib.error
import urllib.request

MANIFEST = sys.argv[1]
DEST = sys.argv[2]

USER_AGENT = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
ATTEMPTS = 3


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def download(url, target):
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=120) as response, open(target, "wb") as out:
        while chunk := response.read(1 << 20):
            out.write(chunk)


manifest = json.load(open(MANIFEST))
ok = skipped = failed = 0

for version in manifest["versions"]:
    vdir = os.path.join(DEST, f"version-{version['version']}")
    os.makedirs(vdir, exist_ok=True)
    for f in version["files"]:
        target = os.path.join(vdir, f["filename"])
        if os.path.exists(target) and sha256(target) == f["sha256"]:
            print(f"  skip (verified)   v{version['version']}  {f['filename']}", flush=True)
            skipped += 1
            continue

        for attempt in range(1, ATTEMPTS + 1):
            print(f"  downloading       v{version['version']}  {f['filename']}"
                  f"  ({f['size_bytes']/1e6:.1f} MB)"
                  f"{'' if attempt == 1 else f'  [attempt {attempt}]'}", flush=True)
            try:
                download(f["download_url"], target)
            except Exception as exc:
                print(f"    error: {exc}", flush=True)
                time.sleep(3 * attempt)
                continue

            got = sha256(target)
            if got == f["sha256"]:
                ok += 1
                break
            print(f"    CHECKSUM MISMATCH\n      expected {f['sha256']}\n      got      {got}", flush=True)
            time.sleep(3 * attempt)
        else:
            print(f"  GAVE UP           v{version['version']}  {f['filename']}", flush=True)
            failed += 1

print(f"\nDONE  downloaded={ok}  already_present={skipped}  failed={failed}")
