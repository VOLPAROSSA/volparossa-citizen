"""Check the generated Citizen page and reconcile its counts with the actual demo."""
import argparse
import json
import re
import subprocess
import sys
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]
ORIGIN = "https://volparossa.org/volparossa-citizen/"


class Edition(HTMLParser):
    def __init__(self):
        super().__init__()
        self.ids = set()
        self.links = []
        self.assets = []
        self.rows = []
        self.numbers = []
        self.dates = []
        self.meta = {}
        self.headings = []
        self.images = []
        self.buffer = None
        self.caption = ""
        self.canonical = None

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if "id" in a:
            assert a["id"] not in self.ids
            self.ids.add(a["id"])
        if tag in ("h1", "h2"):
            self.headings.append(tag)
        if tag == "a":
            self.links.append(a["href"])
        if tag == "link":
            if a["rel"] == "canonical":
                self.canonical = a["href"]
            else:
                self.assets.append(a["href"])
        if tag == "script":
            self.assets.append(a["src"])
        if tag == "meta":
            self.meta[a.get("name") or a.get("property")] = a.get("content")
        if tag == "img":
            self.assets.append(a["src"])
            self.images.append(a)
        if tag == "source":
            self.assets.extend(v.strip().split()[0] for v in a["srcset"].split(","))
        if tag == "time":
            self.dates.append(a["datetime"])
        if tag == "tr":
            self.rows.append([])
        if tag in ("th", "td", "dd", "caption"):
            self.buffer = ""
        if tag == "th":
            assert a["scope"] == "col"

    def handle_data(self, data):
        if self.buffer is not None:
            self.buffer += data

    def handle_endtag(self, tag):
        if tag in ("th", "td"):
            self.rows[-1].append(self.buffer.strip())
        elif tag == "dd":
            self.numbers.append(int(self.buffer))
        elif tag == "caption":
            self.caption = self.buffer.strip()
        else:
            return
        self.buffer = None


def check(folder, production):
    html = (folder / "index.html").read_text()
    edition = Edition()
    edition.feed(html)
    assert '<html lang="en">' in html and "{{" not in html
    assert edition.headings[0] == "h1" and edition.headings.count("h1") == 1
    assert edition.canonical == edition.meta["og:url"] == ORIGIN
    assert edition.meta["robots"] == ("index,follow" if production else "noindex,nofollow")
    assert edition.meta["og:title"] == "VOLPAROSSA Citizen | Follow a town proposal"
    assert edition.meta["og:image"] == edition.meta["twitter:image"] == ORIGIN + "assets/citizen/saturday-edition.jpg"
    assert (folder / "assets/citizen/saturday-edition.jpg").is_file()
    for link in edition.links:
        if link.startswith("#"):
            assert link[1:] in edition.ids, link
        else:
            assert urlsplit(link).scheme == "https", link
    for asset in edition.assets:
        assert not urlsplit(asset).netloc and not asset.startswith("/")
        assert (folder / asset).is_file(), asset
    for css_name in ("site.css", "citizen.css"):
        for asset in re.findall(r"url\(['\"]?([^'\")]+)", (folder / "assets" / css_name).read_text()):
            assert (folder / "assets" / asset).is_file(), asset
    photos = [im for im in edition.images if im["src"].startswith("assets/citizen/")]
    assert len(photos) == 5
    assert all(im["alt"].strip() and int(im["width"]) > 0 and int(im["height"]) > 0 for im in photos)
    assert photos[0]["loading"] == "eager" and all(im["loading"] == "lazy" for im in photos[1:])

    demo = json.loads(subprocess.check_output([sys.executable, "-B", ROOT.parent / "citizen.py", "demo"]))
    cases = {x["outcome"]: x for x in demo["cases"]}
    original = demo["before_explicit_request"]
    successor = demo["explicit_successor"]
    n, accounts, support = original["electorate"], original["registered_accounts"], original["support_required"]
    assert edition.numbers == [n, accounts, support - 1, support] == [101, 102, 33, 34]
    assert 3 * (support - 1) < n <= 3 * support
    decision = original["decision_required"]
    assert 3 * (decision - 1) < 2 * n <= 3 * decision
    assert f"Decision threshold: {decision} of {n}." in html
    assert edition.caption == "Three simulated outcomes for the same proposal"
    rows = [["Yes", "No", "Result"]]
    for name in ("indeterminate", "adopted", "rejected"):
        case = cases[name]
        assert case["electorate"] == n and case["proposal_id"] == original["proposal_id"]
        rows.append([str(case["yes"]), str(case["no"]), name.title()])
    assert edition.rows == rows
    assert edition.dates == [original["closes_at"][:10], original["resubmission_not_before"][:10]]
    assert demo["elapsed_time_allows_request"] and original["successor"] is None
    assert successor["proposal_revision"] == original["proposal_revision"]
    assert successor["snapshot_id"] != original["snapshot_id"] and successor["state"] == "collecting_support"
    assert all(successor[k] == 0 for k in ("support", "yes", "no", "abstain"))
    print("Verified the project route, assets, proposal thresholds, all three results and the empty repeat.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "preview/volparossa-citizen")
    parser.add_argument("--production", action="store_true")
    args = parser.parse_args()
    check(args.output, args.production)
