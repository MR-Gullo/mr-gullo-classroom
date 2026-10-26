"""Inspect a tester release as data. Never execute code from a release ZIP."""
import argparse
import hashlib
import json
import re
import stat
import subprocess
import sys
import urllib.request
import zipfile
from html.parser import HTMLParser
from pathlib import Path, PurePosixPath

SITE = "https://mr-gullo.github.io/mr-gullo-classroom/"
BASE = "/mr-gullo-classroom/"
REPO = "MR-Gullo/mr-gullo-classroom"
QA = ("commonTasks", "keyboardUndo", "importExport", "backupRestore",
      "offlineRestart", "updateWithExistingData", "previousVersionReadsUpdatedData")


def require(ok, message):
    if not ok:
        raise ValueError(message)


def digest(data):
    return hashlib.sha256(data).hexdigest()


def valid_tag(tag):
    require(isinstance(tag, str) and re.fullmatch(r"v\d+\.\d+\.\d+-rc\.\d+", tag),
            "Use a tester tag such as v0.1.0-rc.2")
    return tag


def inspect_release_notes(data):
    """Accept only the small, reviewed public changelog, never arbitrary JSON."""
    require(len(data) <= 64 * 1024, "Release notes exceed 64 KiB")
    notes = json.loads(data)
    require(isinstance(notes, dict) and set(notes) == {"schemaVersion", "releases"}
            and type(notes["schemaVersion"]) is int and notes["schemaVersion"] == 1,
            "Unexpected release notes fields")
    releases = notes["releases"]
    require(isinstance(releases, list) and 1 <= len(releases) <= 50,
            "Unexpected release notes count")
    tags = set()
    for release in releases:
        require(isinstance(release, dict) and set(release) == {"tag", "changes"},
                "Unexpected release notes entry")
        tag = valid_tag(release["tag"])
        require(tag not in tags, "Duplicate release notes tag")
        tags.add(tag)
        changes = release["changes"]
        require(isinstance(changes, list) and 1 <= len(changes) <= 30,
                "Unexpected release changes count")
        for change in changes:
            require(isinstance(change, str) and 0 < len(change.strip()) <= 500
                    and not any(ord(c) < 32 for c in change),
                    "Release changes must be concise plain text")
    require(b"/Users/gullo/" not in data and b"AUDIT-NEW" not in data,
            "Private path or audit marker in release notes")
    return notes


class Head(HTMLParser):
    def __init__(self):
        super().__init__()
        self.robots = []
        self.scripts = []
        self.manifests = []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "meta" and attrs.get("name", "").lower() == "robots":
            self.robots.extend(attrs.get("content", "").replace(" ", "").split(","))
        if tag == "script":
            self.scripts.append(attrs.get("src", ""))
        if tag == "link" and attrs.get("rel") == "manifest":
            self.manifests.append(attrs.get("href", ""))


def inspect_archive(archive):
    archive = Path(archive)
    require(archive.stat().st_size <= 32 * 1024 * 1024, "Archive exceeds 32 MiB")
    files, names = {}, set()
    root_names = {"index.html", "sw.js", "manifest.webmanifest", "_headers",
                  "HOSTING.txt", "third-party-notices.txt", "robots.txt",
                  "release-notes.json"}
    with zipfile.ZipFile(archive) as z:
        require(0 < len(z.infolist()) <= 128, "Unexpected ZIP entry count")
        total = 0
        for info in z.infolist():
            name = info.filename
            path = PurePosixPath(name)
            require(name and not info.is_dir() and not path.is_absolute()
                    and "\\" not in name and ":" not in name
                    and all(p not in ("", ".", "..") for p in name.split("/")),
                    "Unsafe ZIP path")
            require(name.casefold() not in names, "Duplicate or case-colliding ZIP path")
            names.add(name.casefold())
            mode = info.external_attr >> 16
            require(not stat.S_ISLNK(mode) and (not stat.S_IFMT(mode)
                    or stat.S_ISREG(mode)), "ZIP contains a link or special file")
            allowed = (name in root_names
                       or re.fullmatch(r"workbox-[A-Za-z0-9_-]+\.js", name)
                       or re.fullmatch(r"assets/[A-Za-z0-9._-]+\.(js|mjs|css|wasm)", name)
                       or re.fullmatch(r"icons/(192x192|512x512)\.png", name)
                       or re.fullmatch(r"ocr/(LICENSE-[A-Za-z0-9._-]+\.txt|[A-Za-z0-9._-]+\.js|lang/eng\.traineddata\.gz)", name))
            require(allowed, "Unexpected file in app archive: " + name)
            total += info.file_size
            require(info.file_size <= 16 * 1024 * 1024 and total <= 64 * 1024 * 1024,
                    "Uncompressed archive exceeds release limits")
            require(not info.flag_bits & 1, "Encrypted archives are unsupported")
            data = z.read(info)  # CRC checked by zipfile; bounded above before allocation.
            if name == "release-notes.json":
                inspect_release_notes(data)
            if name.endswith((".html", ".js", ".mjs", ".txt")):
                require(b"/Users/gullo/" not in data and b"AUDIT-NEW" not in data,
                        "Private path or audit marker in archive")
            files[name] = data
    require({"index.html", "sw.js", "manifest.webmanifest", "icons/192x192.png",
             "icons/512x512.png", "third-party-notices.txt"} <= files.keys(),
            "Required PWA files are missing")
    require(any(re.fullmatch(r"assets/classroom_engine_bg-[\w-]+\.wasm", n) for n in files),
            "Classroom engine WASM missing")
    require(any(re.fullmatch(r"assets/sqlite3-[\w-]+\.wasm", n) for n in files),
            "SQLite WASM missing")
    manifest = json.loads(files["manifest.webmanifest"])
    require(manifest.get("start_url") == "./" and manifest.get("scope") == "./"
            and manifest.get("display") == "standalone", "Unexpected PWA scope")
    head = Head()
    head.feed(files["index.html"].decode("utf-8"))
    require({"noindex", "nofollow"} <= set(head.robots), "Tester no-index tags missing")
    require(head.scripts and all(s.startswith(BASE + "assets/") for s in head.scripts),
            "Scripts must use the permanent Pages path, without inline scripts")
    require(head.manifests == [BASE + "manifest.webmanifest"], "Wrong manifest path")
    for url in head.scripts:
        require(url[len(BASE):] in files, "Referenced script missing")
    return files


def verify_receipt(archive, receipt, baseline=None):
    require(receipt.get("schemaVersion") == 1, "Unsupported release receipt")
    valid_tag(receipt.get("tag"))
    require(receipt.get("repository") == REPO and receipt.get("site") == SITE,
            "Receipt targets a different repository or site")
    require(re.fullmatch(r"[a-f0-9]{40}", receipt.get("sourceCommit", "")),
            "Missing exact source commit")
    require(Path(archive).stat().st_size <= 32 * 1024 * 1024, "Archive exceeds 32 MiB")
    data = Path(archive).read_bytes()
    require(receipt.get("sha256") == digest(data) and receipt.get("bytes") == len(data),
            "Archive does not match the tested receipt")
    files = inspect_archive(archive)
    require(receipt.get("files") == {n: digest(b) for n, b in files.items()},
            "File inventory does not match the tested receipt")
    if receipt.get("kind") == "adopted-baseline":
        require(baseline is not None and receipt == baseline,
                "Baseline must exactly match the trusted baseline in the workflow")
    else:
        require(receipt.get("kind") == "candidate", "Unknown receipt type")
        require(set(receipt) == {"schemaVersion", "kind", "tag", "repository", "site",
                                "sourceCommit", "createdAt", "sha256", "bytes", "files",
                                "automatedChecks", "rollbackTo", "qa"},
                "Receipt contains unexpected or missing public fields")
        require(receipt.get("automatedChecks") == {"npmCheck": True, "package": True,
                                                  "releaseGuards": True},
                "Full automated checks have not passed")
        qa = receipt.get("qa")
        require(isinstance(qa, dict) and qa.get("checks") == {n: True for n in QA},
                "Artifact-bound manual QA is incomplete")
        require(set(qa) == {"checks", "evidenceSha256"},
                "QA receipt may contain only check results and an evidence fingerprint")
        require(re.fullmatch(r"[a-f0-9]{64}", qa.get("evidenceSha256", "")),
                "Missing private QA evidence fingerprint")
        require(re.fullmatch(r"[a-f0-9]{64}", receipt.get("rollbackTo", "")),
                "Missing tested rollback target")
    return files


def check_transition(receipt, current, mode, expected):
    if mode == "verify":
        return
    require(re.fullmatch(r"[a-f0-9]{64}", expected or ""), "Expected live SHA-256 required")
    require(current.get("sha256") == expected, "Live version changed; re-review this update")
    require(receipt["sha256"] != expected, "Target is already live")
    if mode == "promote":
        require(receipt["kind"] == "candidate" and receipt["rollbackTo"] == expected,
                "Candidate was not tested against the current live build")
    elif mode == "rollback":
        require(current.get("rollbackTo") == receipt["sha256"],
                "Current release does not attest data-safe rollback to this target")
    else:
        raise ValueError("Unknown transition mode")


def current_version():
    request = urllib.request.Request(SITE + "version.json", headers={"Cache-Control": "no-cache"})
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.load(response)


def download_release(tag, directory):
    valid_tag(tag)
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=False)
    meta = json.loads(subprocess.check_output(
        ["gh", "release", "view", tag, "--repo", REPO, "--json", "tagName,assets"], text=True))
    require(meta.get("tagName") == tag, "Release tag mismatch")
    assets = meta.get("assets", [])
    require(len({a["name"] for a in assets}) == len(assets), "Duplicate release assets")
    limits = {"mr-gullo-classroom-pwa.zip": 32 * 1024 * 1024,
              "release-receipt.json": 64 * 1024}
    require(any(a["name"] == "mr-gullo-classroom-pwa.zip" for a in assets), "Hosting ZIP missing")
    for asset in assets:
        if asset["name"] in limits:
            require(0 < asset["size"] <= limits[asset["name"]], "Release asset exceeds size limit")
            subprocess.run(["gh", "release", "download", tag, "--repo", REPO,
                            "--pattern", asset["name"], "--dir", str(directory)], check=True)


def materialize(files, receipt, output):
    output = Path(output)
    output.mkdir(parents=True, exist_ok=False)
    for name, data in files.items():
        target = output / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
    (output / ".nojekyll").write_text("")
    # Public marker is outside the service-worker precache. No teacher data is read.
    marker = dict(receipt, version=receipt["tag"].removeprefix("v"))
    (output / "version.json").write_text(json.dumps(marker, indent=2) + "\n")


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--archive", required=True)
    p.add_argument("--receipt", required=True)
    p.add_argument("--baseline", required=True)
    p.add_argument("--tag", required=True)
    p.add_argument("--mode", choices=("verify", "promote", "rollback"), default="verify")
    p.add_argument("--expected-sha", default="")
    p.add_argument("--output", required=True)
    p.add_argument("--download", action="store_true")
    args = p.parse_args()
    if args.download:
        require(Path(args.archive).parent == Path(args.receipt).parent,
                "Release assets must share a directory")
        download_release(args.tag, Path(args.archive).parent)
    baseline = json.loads(Path(args.baseline).read_text())
    receipt_path = Path(args.receipt)
    receipt = json.loads(receipt_path.read_text()) if receipt_path.exists() else baseline
    require(receipt["tag"] == valid_tag(args.tag), "Release tag and receipt differ")
    files = verify_receipt(args.archive, receipt, baseline)
    check_transition(receipt, current_version(), args.mode, args.expected_sha)
    materialize(files, receipt, args.output)
    print(json.dumps({"tag": receipt["tag"], "sha256": receipt["sha256"],
                      "files": len(files), "mode": args.mode}))


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        print("Release refused: " + str(error), file=sys.stderr)
        sys.exit(1)
