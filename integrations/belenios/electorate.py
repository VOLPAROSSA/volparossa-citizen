# SPDX-License-Identifier: GPL-3.0-only
"""Public electorate declaration carried by the authenticated Belenios description."""
import json
from citizen import MAX_IDENTITIES, label, require, utc

PREFIX = "VOLPAROSSA-Citizen-Electorate/"
V1 = PREFIX + "1 "


def opening_description(text, electorate):
    public = {"eligible": len(electorate.all_eligible), "jurisdiction": electorate.jurisdiction,
              "reference_at": electorate.reference_at, "snapshot_id": electorate.snapshot_id}
    return text + "\n" + V1 + json.dumps(public, sort_keys=True, separators=(",", ":"))


def opening_electorate(description):
    lines = [line for line in description.splitlines() if line.startswith(PREFIX)]
    if not lines:
        return None
    require(len(lines) == 1 and lines[0].startswith(V1), "ambiguous or unsupported opening electorate")
    data = json.loads(lines[0][len(V1):])
    require(isinstance(data, dict) and set(data) == {"eligible", "jurisdiction", "reference_at", "snapshot_id"}
            and lines[0] == V1 + json.dumps(data, sort_keys=True, separators=(",", ":")),
            "invalid opening electorate declaration")
    require(type(data["eligible"]) is int and 1 <= data["eligible"] <= MAX_IDENTITIES,
            "invalid opening eligible population")
    label(data["jurisdiction"])
    label(data["snapshot_id"])
    utc(data["reference_at"])
    return data
