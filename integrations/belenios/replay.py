# SPDX-License-Identifier: GPL-3.0-only
"""Recheck the three fictional public archive pairs with Belenios 3.3.0."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile
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
    from belenios_demo import Tool
    from integrations.belenios.tally import verified_tally
    tool = Tool(executable)
    with ZipFile(bundle) as z, tempfile.TemporaryDirectory() as scratch:
        root = Path(scratch)
        require(tool(root, "--version").split()[:1] == [b"3.3.0"], "requires Belenios 3.3.0")
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
        outcomes = []
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

            tally = verified_tally(tool, setup, final, 6)
            require(tally["election_name"] == "sim-library-hours" and tally["question"] ==
                    "Extend the fictional library's Saturday hours?" and tally["public_credentials"] == 5,
                    f"{case}: unexpected referendum setup")
            require([row[k] for k in ("electorate", "registered_accounts", "support", "support_required",
                                      "decision_required", "not_voted")] == [6, 5, 2, 2, 4, tally["not_voted"]],
                    f"{case}: Citizen fixture rules differ")
            require([tally[k] for k in ("yes", "no", "abstain")] == counts == [row["yes"], row["no"], row["abstain"]]
                    and row["verified_ballots"] == tally["verified_ballots"] and case == tally["outcome"],
                    f"{case}: tally or ballot count differs")
            outcomes.append(f"{case}: {tally['verified_ballots']} verified ballots, yes/no/abstain {counts}")
        print("\n".join(outcomes))


if __name__ == "__main__":
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("bundle", type=Path)
    parser.add_argument("--tool", default="belenios-tool")
    parser.add_argument("--setup-pin", type=Path, help="separately trusted public setup digest file")
    args = parser.parse_args()
    verify(args.tool, args.bundle, args.setup_pin)
