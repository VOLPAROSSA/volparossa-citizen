# VOLPAROSSA Citizen · The Saturday Edition

The static English project page follows the fictional library-hours proposal from
support collection to a referendum result and a possible repeat. The builder
reads the real Citizen demo at build time and prints its outcomes as an HTML
table. Visitors can inspect the example without an account or JavaScript.

## Build and preview

Run these commands from the repository root with Python 3.10 or newer.

```sh
python3 -B citizen.py demo
python3 -B -m unittest discover -s tests -v
python3 website/scripts/build_site.py
python3 website/scripts/check_site.py
python3 -m http.server 8799 --bind 127.0.0.1 --directory website/preview
```

Open http://127.0.0.1:8799/volparossa-citizen/. Preview pages request no indexing.
The existing GitHub Pages Actions source serves the production artifact at
https://volparossa.org/volparossa-citizen/.

```sh
python3 website/scripts/build_site.py --production --output website/dist/volparossa-citizen
python3 website/scripts/check_site.py --production --output website/dist/volparossa-citizen
```

The Citizen website workflow saves the preview and browser screenshots as a PR
artifact, then builds and deploys the checked site on main. It can also be run
manually. Source, artwork and review renders live under website/. The publication
workflow is in .github/workflows/citizen-website.yml.

## Review

[Desktop render](review/desktop.webp) · [Mobile render](review/mobile.webp)

With the preview server running, use Node 24 and an installed Chromium. Set
CHROME_PATH to its executable.

```sh
npm --prefix website ci --ignore-scripts
CHROME_PATH=/usr/bin/chromium npm --prefix website run qa
```

QA_ENGINES can select firefox or webkit with the matching Playwright browsers
installed. QA_URL can point to the public project URL.

The checks cover 1440, 768, 390 and 320 CSS pixels, 200% text enlargement, the
skip link, keyboard focus, dropdown and mobile navigation, direct fragment
reloads and the native disclosures. The browser's accessibility tree exposes
one lead heading and three outcome rows under their column headers. Chromium
also runs the automated WCAG A/AA audit. The page was compared with the
reference at desktop and phone sizes, including the library entrance, the
two pairs of figures, the comparison table and the archive documents.

The static checker compares the HTML with the simulation. The fixed electorate
contains 101 eligible residents and there are 102 registered accounts. Exactly
34 distinct supporters open voting. The three results in reading order are
67/34 indeterminate, 68/33 adopted and 33/68 rejected. The original result
remains closed when the repeat first becomes possible on 1 December 2029.
The requested successor has the same proposal revision, a new electorate
snapshot and no support or ballots. All people and procedure dates in the
example are fictional. The 21 existing simulation tests cover the procedure
including integer thresholds, time boundaries and abstention.

## Sources and rights

The reporting uses the README, citizen.py demo and its tests at [Citizen
revision 6417e4d](https://github.com/VOLPAROSSA/volparossa-citizen/tree/6417e4de51f68480426f6868b8a160dfffa56f2e).
Saturday afternoons are the editorial detail supplied for the library proposal.
The masthead, red rules, column sequence and photographic subjects follow the
owner-supplied “Concept 04 — De stadskrant”. The concept mockup is not shipped.

Four black-and-white photographic compositions were generated with AI for
this page using the supplied visual reference. They show the fictional
neighbourhood library, the archive box beside a blank form, a town street and
a hand with an unmarked slip. The archive and form are separately cropped
from the same two-panel composition and captioned in HTML. The library is
also used for the 1200 × 630 social image with the edition's typeset masthead.
Local WebP derivatives and JPEG fallbacks are in assets/citizen. These original
site materials are distributed under the repository licence to the extent
rights apply.

The shared header, menu, footer, mark, favicon, fonts and tokens are the
source-only 1.1.0 theme export from [central revision 9593bc9](https://github.com/VOLPAROSSA/volparossa.github.io/tree/9593bc9025d1674ce0982e425feb0d90ba8467e7).
The builder verifies its file checksums. The newspaper also uses the Latin bold
and bold italic cuts of Cormorant Garamond from Google Fonts v21, served locally
under the [SIL Open Font License](vendor/theme/assets/fonts/cormorant-garamond-LICENSE.txt).
The additional binaries come from the [roman](https://fonts.gstatic.com/s/cormorantgaramond/v21/co3umX5slCNuHLi8bLeY9MK7whWMhyjypVO7abI26QOD_hg9KnTOig.woff2)
and [italic](https://fonts.gstatic.com/s/cormorantgaramond/v21/co3smX5slCNuHLi8bLeY9MK7whWMhyjYrGFEsdtdc62E6zd5FTf-iNM8.woff2)
distributions. Font licences, the GitHub icon licence, theme notices and the
repository GPL-3.0-only licence retain their original terms.
