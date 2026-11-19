# SPDX-License-Identifier: GPL-3.0-only
"""Recheck the three fictional public archive pairs with Belenios 3.3.0."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import tarfile
from zipfile import ZipFile

EXPECTED = {"adopted": [4, 0, 1], "indeterminate": [3, 0, 1], "rejected": [1, 4, 0]}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def verify_cached(core, tool, manifest, publisher_key, caches, setup_pin):
    require(len(publisher_key) == 64 and all(c in "0123456789abcdefABCDEF" for c in publisher_key),
            "expected a 32-byte public publisher key in hexadecimal")
    require(1 <= len(caches) <= 16 and all(Path(path).is_dir() for path in caches),
            "expected 1 through 16 existing local Core caches")
    require(Path(setup_pin).is_file(), "independently retained setup pin unavailable")
    with tempfile.TemporaryDirectory() as scratch:
        bundle = Path(scratch) / "public-referenda.zip"
        command = [core, "content", "assemble", "--manifest", manifest, "--publisher-key", publisher_key,
                   "--output", str(bundle)]
        for path in caches:
            command.extend(["--cache", path])
        receipt = json.loads(subprocess.check_output(command, stdin=subprocess.DEVNULL, timeout=120))
        require(isinstance(receipt, dict) and receipt.get("operation") == "offline_content_assemble"
                and receipt.get("network_retrieval") is False and receipt.get("publisher_key_hex") == publisher_key.lower()
                and receipt.get("output") == str(bundle) and receipt.get("bytes") == bundle.stat().st_size,
                "Core did not confirm the local publisher-bound archive")
        verify(tool, bundle, setup_pin)


def verify(executable, bundle, setup_pin=None):
    matches = shutil.which(executable)
    require(matches, "Belenios executable unavailable")
    tool = str(Path(matches).resolve())
    with ZipFile(bundle) as z, tempfile.TemporaryDirectory() as scratch:
        root = Path(scratch)
        env = {"PATH": os.defpath, "HOME": scratch, "TMPDIR": scratch, "LC_ALL": "C"}
        version = subprocess.check_output([tool, "--version"], cwd=root, env=env, timeout=30)
        require(version.split()[:1] == [b"3.3.0"], "requires Belenios 3.3.0")
        allowed = {"report.json"} | {f"{case}/{stage}/election.bel" for case in EXPECTED
                                      for stage in ("setup", "final")}
        require(len(z.infolist()) == len(allowed) and set(z.namelist()) == allowed
                and all(item.file_size <= 1024 * 1024 for item in z.infolist()), "unexpected bundle contents")
        if setup_pin is not None:
            with Path(setup_pin).open("rb") as witness:
                data = witness.read(1025)
            require(len(data) <= 1024, "unexpected setup pin size")
            hashes = {case: hashlib.sha256(z.read(f"{case}/setup/election.bel")).hexdigest() for case in EXPECTED}
            require(json.loads(data) == {"schema": "volparossa.citizen.belenios-setup.v1", "sha256": hashes},
                    "referendum setup differs from the independently retained pin")
        report = json.loads(z.read("report.json"))
        rows = report["cases"]
        require(report["schema"] == "volparossa.citizen.belenios-demo.v1" and
                [row["outcome"] for row in rows] == list(EXPECTED), "unexpected case manifest")
        for row in rows:
            case = row["outcome"]
            counts = EXPECTED[case]
            for stage in ("setup", "final"):
                path = root / case / stage / "election.bel"
                path.parent.mkdir(parents=True)
                path.write_bytes(z.read(f"{case}/{stage}/election.bel"))
            setup, final = root / case / "setup", root / case / "final"
            archived = hashlib.sha256((final / "election.bel").read_bytes()).hexdigest()
            require(archived == row["public_archive_sha256"], f"{case}: archive digest differs")

            def run(*args):
                return subprocess.check_output([tool, "election", *args], cwd=final, env=env, timeout=30)

            run("verify-diff", "--dir1", setup, "--dir2", final)
            checksums = json.loads(run("compute-checksums"))
            require(checksums.get("final") and checksums.get("encrypted_tally")
                    and checksums["num_voters"] == 5, f"{case}: missing closed election or credentials")
            with tarfile.open(setup / "election.bel", "r:") as archive:
                election = archive.getmember(checksums["election"] + ".data.json")
                require(election.isfile(), "unexpected election definition")
                definition = json.load(archive.extractfile(election))
            require(definition["name"] == "sim-library-hours" and definition["group"] == "Ed25519"
                    and definition["questions"] == [{"question": "Extend the fictional library's Saturday hours?",
                        "answers": ["Yes", "No", "Abstain"], "min": 1, "max": 1}],
                    f"{case}: unexpected referendum question or answer order")
            require([row[k] for k in ("electorate", "registered_accounts", "support", "support_required",
                                      "decision_required", "not_voted")] == [6, 5, 2, 2, 4, 6 - sum(counts)],
                    f"{case}: Citizen fixture rules differ")
            require(json.loads(run("compute-result"))["result"] == [counts]
                    and [row["yes"], row["no"], row["abstain"]] == counts
                    and len(json.loads(run("compute-ballot-summary"))) == row["verified_ballots"] == sum(counts),
                    f"{case}: tally or ballot count differs")
            print(f"{case}: {sum(counts)} verified ballots, yes/no/abstain {counts}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("bundle", type=Path)
    parser.add_argument("--tool", default="belenios-tool")
    parser.add_argument("--setup-pin", type=Path, help="separately trusted public setup digest file")
    args = parser.parse_args()
    verify(args.tool, args.bundle, args.setup_pin)
