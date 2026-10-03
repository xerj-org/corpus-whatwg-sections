# corpus-whatwg-sections

Section-split mirror of the WHATWG **HTML** and **URL** living-standard source
repositories, shaped for retrieval corpora. Each spec section is one text file
with a breadcrumb header and the verbatim spec-source text of that section.

This exists because whole-file indexing of these repositories loses: the
`whatwg/html` spec source is a single ~7.9 MB file (`source`) that an indexer
skips outright, and `review-drafts/*` are dated near-duplicate snapshots that
crowd out real hits. Splitting one file per section with a breadcrumb header
fixes both (see the Corpus Hub G7 measurement and the pre-registered shaping in
its `WAVES.md`).

## Provenance

| Spec | Upstream | Pinned SHA | Upstream commit date | Source file | Source size |
|------|----------|------------|----------------------|-------------|-------------|
| HTML | https://github.com/whatwg/html | `6992cb519a02db34f653ddd54c50fad2565285f5` | 2026-10-01 | `source` | 7,923,481 B |
| URL  | https://github.com/whatwg/url  | `8e14777cfa145b08a9fb735fe580ec0c366564c3` | 2026-09-10 | `url.bs`    | 166,059 B |

Both upstream repositories are Bikeshed (`*.bs`) sources; `whatwg/html` keeps
its source in a file named `source`.

## Licence

Each upstream `LICENSE` is copied verbatim: [`html/LICENSE`](html/LICENSE) and
[`url/LICENSE`](url/LICENSE). Both files state: copyright WHATWG (Apple,
Google, Mozilla, Microsoft); the text is licensed under **Creative Commons
Attribution 4.0 International (CC-BY-4.0)**, and portions incorporated into
source code are licensed under the **BSD 3-Clause License** instead. The spec
text mirrored here is CC-BY-4.0.

## Layout

```
html/sections/<section>.txt   753 files (incl. _preamble.txt)
url/sections/<section>.txt     36 files (incl. _preamble.txt)
html/LICENSE, url/LICENSE      verbatim upstream licences
tools/split_spec.py            the exact splitter used (regeneration tool)
README.md
```

Nothing else from the upstream clones is mirrored: `review-drafts/`, `.git/`,
build outputs, `images/`, `fonts/`, `demos/`, `dev/`, styles, scripts, and the
raw single-file sources are all excluded — only the split live-spec text and
the licences are here.

## File format

Line 1 is a breadcrumb header:

```
WHATWG <SPEC> — section <id> — <heading text as written>
```

for example `WHATWG URL — section url-parsing — URL parsing`. Line 2 is blank.
From line 3 on, the file is the **byte-for-byte verbatim** source text of that
section (whitespace unchanged, UTF-8, LF) — downstream grading greps exact
clauses against these files. Section ids whose breadcrumb shows a chain
(`a/b/c`) come from the sub-splitting described below.

## Shaping rules (as implemented)

1. Split on `<h2 id=…>`, `<h3 id=…>`, `<h4 id=…>` heading lines (attributes
   quoted or unquoted). Each file is named by the heading's `id=` value,
   sanitized to a safe filename. 456 of html's 622 headings carry no `id=`;
   those are named by a slug of the heading text, with a numeric suffix on
   collision. Sub-split chunks are named `<parent>__<chunk>`.
2. A section whose body exceeds ~150 KB is re-split on its `<dt id=…>`
   anchors. For HTML this hit 3 sections.
3. **Rule-6 extension (disclosed):** where a section still exceeded ~150 KB
   after the dt split — because it contains no further `h4` headings to split
   on — it was split on its next finer real headings, `<h5>`/`<h6>` (4
   sections), and where no headings existed at all, on its plain `<dt>` lines
   (1 section: `dependencies`, 75 chunks). The fixed-size line-boundary last
   resort implemented in the script never triggered. Affected top-level
   sections: `dependencies`, `images`, `media-elements` (handling first
   frame), `navigation-api`, `the-canvas-element`, `the-input-element`,
   `tree-construction`.
4. Sections smaller than ~200 bytes were merged into the previous file, noted
   in that file's header by appending `(+<id>)` — 61 merged in HTML, 0 in URL.
5. Everything before the first `<h2>` is `_preamble.txt` in each spec.

### Result

| Spec | Section files | Largest file | Files > 150 KB |
|------|---------------|--------------|----------------|
| HTML | 753           | `images__images.txt`, 148,751 B | 0 |
| URL  | 36            | `url-parsing.txt`, 35,148 B     | 0 |

No file in this repository exceeds 150 KB (verified with
`find html url -type f -size +150000c` → empty).

## Verbatim guarantee

The splitter asserts, on every run, that the concatenation of all section
bodies (in source order, headers stripped) is byte-identical to the upstream
source file — so every clause of the upstream text exists, unchanged, in
exactly one section file. Spot check: `This specification should be read`
occurs once in html's `source` and once in
`html/sections/how-to-read-this-specification.txt`.

## Regenerating

```sh
git clone https://github.com/whatwg/html && cd html && git checkout 6992cb519a02db34f653ddd54c50fad2565285f5
git clone https://github.com/whatwg/url  && cd url  && git checkout 8e14777cfa145b08a9fb735fe580ec0c366564c3
python3 tools/split_spec.py html/source HTML html/sections 622
python3 tools/split_spec.py url/url.bs   URL  url/sections  35
```

(The trailing argument is the expected h2/h3/h4 heading count, as a parse
sanity check.) The script re-creates `html/sections/` and `url/sections/`
from scratch, prints merge/fallback stats, and fails loudly if the
reconstruction is not byte-identical or any file exceeds 150 KB.
