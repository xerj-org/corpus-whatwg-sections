#!/usr/bin/env python3
"""Split a WHATWG Bikeshed spec source into one file per section.

Shaping rules (pre-registered in the Corpus Hub WAVES.md):

  1. Split on <h2>/<h3>/<h4> heading lines. A section whose body exceeds
     GIANT bytes is re-split on its <dt id=...> anchors; if a piece is STILL
     over GIANT, it is split on its <h5>/<h6> heading lines, then on plain
     <dt> lines, and only as a last resort at line boundaries into fixed-size
     parts (never expected to trigger; reported if it does).
  2. Each file: one breadcrumb header line, a blank line, then the VERBATIM
     source bytes of that section (whitespace unchanged).
  3. Top-level sections smaller than MERGE bytes are merged into the previous
     file, noted in its header line by appending (+<id>).
  4. Everything before the first h2 becomes _preamble.txt.
  5. Proof of verbatim-ness: the concatenation of all section bodies, in span
     order, is asserted byte-identical to the input file.

Naming: top-level files are named by the heading's id= value (sanitized to a
safe filename); headings without id= get a slug of their heading text, with a
numeric suffix on collision. Sub-split chunks are named <parent>__<chunk>,
where <chunk> is the dt id, the h5/h6 id (or slug), the dt slug, or partN.

Usage: split_spec.py <source-file> <SPEC-NAME> <output-dir> [<expected-h234-count>]
"""
import bisect
import hashlib
import os
import re
import sys

GIANT = 150 * 1024
MERGE = 200
PART = 128 * 1024  # last-resort fixed chunk size (leaves headroom under GIANT)

HEAD_RE = re.compile(r'<h([234])(?=[\s>])')
H56_RE = re.compile(r'<h([56])(?=[\s>])')
ID_RE = re.compile(r'\bid\s*=\s*(?:"([^"]*)"|\'([^\']*)\'|([^\s>]+))')
DT_ID_RE = re.compile(r'<dt\s+id\s*=\s*(?:"([^"]*)"|\'([^\']*)\'|([^\s>]+))')
DT_ANY_RE = re.compile(r'<dt(?=[\s>])')


def open_tag_end(text, pos):
    """Index of the '>' closing the tag that starts at text[pos]=='<', honoring quotes."""
    i = pos + 1
    in_q = None
    while i < len(text):
        c = text[i]
        if in_q:
            if c == in_q:
                in_q = None
        elif c in ('"', "'"):
            in_q = c
        elif c == '>':
            return i
        i += 1
    return -1


def collapse(s):
    return re.sub(r'\s+', ' ', s).strip()


def sanitize(name):
    s = re.sub(r'[^A-Za-z0-9._-]+', '-', name)
    s = re.sub(r'-{2,}', '-', s).strip('-.')
    if len(s) > 100:
        s = s[:80] + '-' + hashlib.sha1(name.encode()).hexdigest()[:8]
    return s or 'unnamed'


def slug(text):
    t = re.sub(r'<[^>]+>', '', text)
    t = re.sub(r'&[A-Za-z#0-9]+;', ' ', t)
    s = '-'.join(w.lower() for w in re.findall(r'[A-Za-z0-9]+', t))
    if len(s) > 100:
        s = s[:80] + '-' + hashlib.sha1(text.encode()).hexdigest()[:8]
    return s or 'unnamed'


class Namer:
    def __init__(self):
        self.used = {}

    def unique(self, base):
        name = base
        n = self.used.get(base, 0)
        if n:
            name = f'{base}-{n + 1}'
        self.used[base] = n + 1
        return name


def line_starts_of(span):
    starts = [0]
    for i, c in enumerate(span):
        if c == '\n':
            starts.append(i + 1)
    return starts


def tag_text(span, m, closing):
    """Heading/term text between the end of the opening tag at m and its closing tag."""
    tag_end = open_tag_end(span, m.start())
    if tag_end < 0:
        return ''
    close = span.find(closing, tag_end + 1)
    if close < 0 or close - tag_end > 4000:
        close = min(tag_end + 300, len(span))
    return collapse(span[tag_end + 1:close])


def anchor_line(span, m, starts):
    li = bisect.bisect_right(starts, m.start()) - 1
    return starts[li]


def find_headings(text):
    """h2/h3/h4 headings: list of (line_start, id_or_None, heading_text)."""
    starts = line_starts_of(text)
    heads = []
    for m in HEAD_RE.finditer(text):
        lvl = m.group(1)
        tag_end = open_tag_end(text, m.start())
        if tag_end < 0:
            continue
        attrs = text[m.start():tag_end + 1]
        head_text = tag_text(text, m, '</h' + lvl)
        idm = ID_RE.search(attrs)
        hid = (idm.group(1) or idm.group(2) or idm.group(3)) if idm else None
        ls = anchor_line(text, m, starts)
        prefix = text[ls:m.start()]
        if prefix.strip() and not re.fullmatch(r'(<!--[^>]*>)+', prefix.strip()):
            print(f'  WARN: heading preceded by content at offset {m.start()}: {prefix!r}',
                  file=sys.stderr)
        heads.append((ls, hid, head_text))
    return heads


def sub_anchors(span):
    """Anchor candidates for giant sections, in fallback priority order.

    Returns a list of (priority, [(line_start, id_or_None, text), ...]) so the
    caller can try the finest-grained anchor set that exists.
    """
    starts = line_starts_of(span)
    out = []
    # priority 0: <dt id=...>
    hits = []
    for m in DT_ID_RE.finditer(span):
        dt_id = m.group(1) or m.group(2) or m.group(3)
        hits.append((anchor_line(span, m, starts), dt_id, tag_text(span, m, '</dt>')))
    if hits:
        out.append((0, hits))
    # priority 1: <h5>/<h6> headings
    hits = []
    for m in H56_RE.finditer(span):
        lvl = m.group(1)
        tag_end = open_tag_end(span, m.start())
        idm = ID_RE.search(span[m.start():tag_end + 1]) if tag_end >= 0 else None
        hid = (idm.group(1) or idm.group(2) or idm.group(3)) if idm else None
        hits.append((anchor_line(span, m, starts), hid, tag_text(span, m, '</h' + lvl)))
    if hits:
        out.append((1, hits))
    # priority 2: any <dt>
    hits = [(anchor_line(span, m, starts), None, tag_text(span, m, '</dt>'))
            for m in DT_ANY_RE.finditer(span)]
    if hits:
        out.append((2, hits))
    return out


class Splitter:
    def __init__(self, text, outdir, spec):
        self.text = text
        self.outdir = outdir
        self.spec = spec
        self.namer = Namer()
        self.entries = []       # (start, end, path_id, text, merged_ids, fallback_note)
        self.stats = {'dt': 0, 'h56': 0, 'dtany': 0, 'part': 0}

    def emit(self, start, end, ident, text_hdr, chain, merged, note):
        size = end - start
        if size <= GIANT:
            base = sanitize(ident) if ident else slug(text_hdr)
            fname_base = '__'.join(chain + [base])
            path_id = '/'.join(chain + [ident or base])
            self.entries.append((start, end, path_id, text_hdr, fname_base, merged, note))
            return
        span = self.text[start:end]
        # try anchor sets in priority order; pick the FIRST that yields >1 piece
        for (prio, hits) in sub_anchors(span):
            bounds = sorted(set(h[0] for h in hits))
            if len(bounds) < 2 and not (bounds and bounds[0] > 0):
                continue
            info = {b: h for h in hits for b in [h[0]]}
            base = sanitize(ident) if ident else slug(text_hdr)
            key = f'{prio}'
            self.stats[{0: 'dt', 1: 'h56', 2: 'dtany'}[prio]] += 1
            pieces = []
            first = bounds[0]
            if first > 0:  # parent heading + intro keeps the parent identity
                pieces.append((0, first, ident, text_hdr, note))
            for j, b in enumerate(bounds):
                e = bounds[j + 1] if j + 1 < len(bounds) else size
                cid, ctext = info[b][1], info[b][2]
                pieces.append((b, e, cid, ctext, key))
            for (b, e, cid, ctext, n) in pieces:
                self.emit(start + b, start + e, cid, ctext,
                          chain + [base], [], n)
            return
        # last resort: fixed-size line-boundary parts
        self.stats['part'] += 1
        starts = [s for s in line_starts_of(span) if s < size]
        idx = 0
        n = 0
        while idx < size:
            n += 1
            nxt = min(idx + PART, size)
            if nxt < size:  # extend/contract to the next line boundary under GIANT
                b = bisect.bisect_right(starts, nxt - 1) - 1
                if starts[b] > idx:
                    nxt = starts[b]
            self.emit(start + idx, start + nxt, f'part{n}', text_hdr, chain, [],
                      'part')
            idx = nxt

    def write(self):
        written = []
        for (start, end, path_id, text_hdr, fname_base, merged, note) in self.entries:
            if len(fname_base) > 180:  # keep the full path under filesystem limits
                fname_base = (fname_base[:160] + '-'
                              + hashlib.sha1(fname_base.encode()).hexdigest()[:12])
            hdr = f'WHATWG {self.spec} — section {path_id} — {text_hdr}'
            for mid in merged:
                hdr += f' (+{mid})'
            body = self.text[start:end]
            fname = self.namer.unique(fname_base) + '.txt'
            with open(os.path.join(self.outdir, fname), 'w',
                      encoding='utf-8', newline='') as f:
                f.write(hdr + '\n\n' + body)
            written.append((start, end, fname, len(hdr.encode('utf-8')) + 2 + end - start,
                            path_id))
        return written


def main():
    src, spec, outdir = sys.argv[1], sys.argv[2], sys.argv[3]
    expected = int(sys.argv[4]) if len(sys.argv) > 4 else None
    os.makedirs(outdir, exist_ok=True)
    text = open(src, encoding='utf-8').read()

    heads = find_headings(text)
    print(f'{spec}: {len(heads)} h2/h3/h4 headings '
          f'({sum(1 for h in heads if h[1])} with id=, {sum(1 for h in heads if not h[1])} slug-named)')
    if expected is not None and len(heads) != expected:
        sys.exit(f'FATAL: expected {expected} headings, parsed {len(heads)}')
    if not heads:
        sys.exit('FATAL: no headings found')

    # raw top-level sections (contiguous, verbatim)
    sections = []
    if heads[0][0] > 0:
        sections.append({'start': 0, 'end': heads[0][0], 'id': '_preamble',
                         'text': 'Front matter before the first section heading',
                         'merged': []})
    for (ls, hid, htext) in heads:
        sections.append({'start': ls, 'end': None, 'id': hid, 'text': htext,
                         'merged': []})
    for i, s in enumerate(sections):
        s['end'] = sections[i + 1]['start'] if i + 1 < len(sections) else len(text)
        s['size'] = s['end'] - s['start']

    # rule 3: merge tiny sections into the previous file
    merged_sections = []
    for s in sections:
        if merged_sections and s['size'] < MERGE and s['id'] != '_preamble':
            prev = merged_sections[-1]
            prev['end'] = s['end']
            prev['size'] += s['size']
            prev['merged'].append(s['id'] or slug(s['text']))
        else:
            merged_sections.append(dict(s))
    print(f'{spec}: {len(sections) - len(merged_sections)} tiny sections merged '
          f'away (<{MERGE} bytes)')

    sp = Splitter(text, outdir, spec)
    for s in merged_sections:
        sp.emit(s['start'], s['end'], s['id'], s['text'], [], s['merged'], None)
    written = sp.write()

    # rule 5 proof: concatenated bodies == source text, byte for byte
    ordered = sorted(written, key=lambda w: w[0])
    recon = []
    for (st, en, fn, sz, pid) in ordered:
        with open(os.path.join(outdir, fn), encoding='utf-8', newline='') as f:
            content = f.read()
        body = content.split('\n\n', 1)[1]
        assert len(body) == en - st, f'body size mismatch in {fn}'
        recon.append(body)
    assert ''.join(recon) == text, 'FATAL: concatenated bodies != source text'
    print(f'{spec}: reconstruction check PASSED — all {len(ordered)} bodies '
          f'concatenate byte-identically to the source')

    over = [(fn, sz) for (_, _, fn, sz, _) in written if sz > GIANT]
    if over:
        print(f'{spec}: FATAL files over {GIANT}B: {over}')
        sys.exit(1)
    largest = max(written, key=lambda w: w[3])
    print(f'{spec}: sections={len(written)} largest={largest[3]}B ({largest[2]})')
    print(f'{spec}: fallback splits — dt-id={sp.stats["dt"]} h5/h6={sp.stats["h56"]} '
          f'dt-any={sp.stats["dtany"]} fixed-part={sp.stats["part"]}')
    with open(os.path.join(outdir, '..', '_manifest_' + spec.lower() + '.txt'), 'w') as f:
        for (st, en, fn, sz, pid) in ordered:
            f.write(f'{sz}\t{fn}\n')


if __name__ == '__main__':
    main()
