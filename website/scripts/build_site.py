"""Build the static Citizen page at the GitHub Pages project path."""
import argparse
import hashlib
import importlib.util
import json
import re
import shutil
import subprocess
import sys
from html import escape
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
THEME = ROOT / "vendor/theme"
SRC = ROOT / "src"
CANONICAL = "https://volparossa.org/volparossa-citizen/"
REPO = "https://github.com/VOLPAROSSA/volparossa-citizen"


def render(template, values):
    return re.sub(r"{{(\w+)}}", lambda match: values[match[1]], template)


def arrows(html):
    paths = {"↗": "M3 13 13 3M5 3h8v8", "→": "M2 8h12m-5-5 5 5-5 5"}
    for char, path in paths.items():
        html = html.replace(char, f'<svg class="direction" width="14" height="14" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5" aria-hidden="true"><path d="{path}"/></svg>')
    return html


def theme_values():
    inventory = json.loads((THEME / "theme-version.json").read_text())
    for name, expected in inventory["files"].items():
        if hashlib.sha256((THEME / name).read_bytes()).hexdigest() != expected:
            raise ValueError(f"Modified shared theme file: {name}")
    spec = importlib.util.spec_from_file_location("navigation", THEME / "shared/navigation.py")
    navigation = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(navigation)
    nav = json.loads((THEME / "data/navigation.json").read_text())
    # Resolve the project’s own entry in the pinned shared navigation.
    for item in nav["main"]:
        for app in item.get("children", []):
            if app["name"] == "Citizen":
                app["url"] = CANONICAL
    projects = json.loads((THEME / "data/projects.json").read_text())
    links = navigation.site_links(nav, projects, "https://volparossa.org/")
    icon = (THEME / "assets/icons/github.svg").read_text().replace("<svg ", '<svg aria-hidden="true" class="github-icon" ', 1)
    links["nav_links"] = navigation.navigation_links(nav["main"], links, "", icon)
    links["footer_links"] = navigation.navigation_links(nav["footer"], links, "", icon, footer=True)
    return links


def illustration(name, widths, height, sizes, alt):
    base = f"assets/citizen/{name}"
    sources = ", ".join(f"{base}-{width}.webp {width}w" for width in widths)
    loading = 'loading="eager" fetchpriority="high"' if name == "library" else 'loading="lazy"'
    return (f'<picture class="press-photo {name}-photo"><source type="image/webp" srcset="{sources}" sizes="{sizes}">'
            f'<img src="{base}.jpg" width="{widths[-1]}" height="{height}" alt="{escape(alt, quote=True)}" '
            f'{loading} decoding="async"></picture>')


def outcome_rows():
    demo = subprocess.check_output([sys.executable, "-B", ROOT.parent / "citizen.py", "demo"], text=True)
    cases = {case["outcome"]: case for case in json.loads(demo)["cases"]}
    rows = []
    for result in ("indeterminate", "adopted", "rejected"):
        case = cases[result]
        rows.append(f'<tr><td>{case["yes"]}</td><td>{case["no"]}</td><td>{result.title()}</td></tr>')
    return "".join(rows)


def build(output, production):
    output.mkdir(parents=True, exist_ok=True)
    marker = output / ".citizen-site-build"
    if any(output.iterdir()):
        if not marker.is_file():
            raise ValueError("Choose an empty directory or an existing Citizen site build.")
        shutil.rmtree(output)
        output.mkdir()
    marker.touch()
    (output / ".nojekyll").touch()
    shutil.copytree(ROOT / "assets", output / "assets")
    for name in ["site.css", "tokens.css", "site.js", "logo.png", "favicon.png"]:
        shutil.copy2(THEME / "assets" / name, output / "assets" / name)
    for name in ["fonts", "icons"]:
        shutil.copytree(THEME / "assets" / name, output / "assets" / name)
    shutil.copy2(THEME / "favicon.ico", output)
    shutil.copy2(SRC / "citizen.css", output / "assets")
    robots = "index,follow" if production else "noindex,nofollow"
    art = json.loads((SRC / "art.json").read_text())
    pictures = {name: illustration(name, **spec) for name, spec in art.items()}
    values = {**theme_values(), **pictures, "outcome_rows": outcome_rows(),
              "title": "VOLPAROSSA Citizen | Follow a town proposal",
              "description": "Follow a fictional library proposal from public support to a referendum. Compare three simulated results and see when a repeat can be requested.",
              "root": "", "canonical": CANONICAL, "body_class": "citizen-page",
              "social_image": CANONICAL + "assets/citizen/saturday-edition.jpg",
              "social_alt": "VOLPAROSSA Citizen, The Saturday Edition, above a black-and-white photograph of the town library.",
              "head_extra": f'<meta name="robots" content="{robots}"><link rel="stylesheet" href="assets/citizen.css">',
              "repository": REPO}
    for part in ["header", "footer"]:
        values[part] = render((THEME / f"templates/{part}.html").read_text(), values)
    values["content"] = render((SRC / "index.html").read_text(), values)
    (output / "index.html").write_text(arrows(render((THEME / "templates/layout.html").read_text(), values)))
    if production:
        (output / "sitemap.xml").write_text(f'<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9"><url><loc>{CANONICAL}</loc></url></urlset>\n')
    print("Built", output)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "preview/volparossa-citizen")
    parser.add_argument("--production", action="store_true")
    args = parser.parse_args()
    build(args.output.resolve(), args.production)
