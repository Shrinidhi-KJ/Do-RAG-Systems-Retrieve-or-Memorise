"""
tei_parser.py
-------------
Turn GROBID TEI-XML into a clean, structured document, applying the KEEP/DROP policy.

KEEP: title (metadata), abstract, and body sections (introduction, methods, results,
      discussion, conclusion, ...) with their headings; figure and table CAPTIONS as
      content, tagged as captions.
DROP: everything in TEI <back> (bibliography/references, acknowledgements, funding,
      annexes), plus any BODY section whose heading matches a drop keyword (conflict of
      interest, data availability, supplementary, appendix, ...). Running headers, page
      footers and page numbers are already excluded by GROBID upstream.

Known limitation: we deliberately do NOT reconstruct table grids. A table contributes
its CAPTION only; the numeric cell grid is not extracted (recorded as a limitation).

Parsing uses the Python standard library (xml.etree.ElementTree) so it adds no
dependency; lxml is not required.
"""

import re
from dataclasses import dataclass, field
from typing import List, Optional
import xml.etree.ElementTree as ET

TEI_NS = "http://www.tei-c.org/ns/1.0"
NS = {"tei": TEI_NS}


@dataclass
class Section:
    label: str          # canonical: introduction/methods/results/discussion/conclusion/abstract/other
    head: str           # raw heading text as printed (may be "")
    text: str           # cleaned paragraph text for this section unit


@dataclass
class Caption:
    kind: str           # "figure" or "table"
    text: str           # caption text


@dataclass
class ParsedDoc:
    title: str = ""
    abstract: str = ""
    tei_doi: Optional[str] = None
    sections: List[Section] = field(default_factory=list)
    captions: List[Caption] = field(default_factory=list)
    dropped_heads: List[str] = field(default_factory=list)   # for auditability

    def n_body_units(self) -> int:
        return len(self.sections) + len(self.captions)


# ---- text helpers -------------------------------------------------------------

def _clean(text: str) -> str:
    """Collapse whitespace. GROBID already dehyphenates line breaks and strips
    headers/footers, so cleaning here is deliberately light."""
    if not text:
        return ""
    text = text.replace("­", "")            # soft hyphens
    text = re.sub(r"\s+", " ", text)             # collapse all whitespace runs
    return text.strip()


def _text_of(elem) -> str:
    """All descendant text of an element (e.g. a <p> with inline <ref>/<hi>)."""
    return _clean("".join(elem.itertext()))


def canonical_label(head: str, label_map) -> str:
    """Map a raw heading to a canonical section label. Unknown -> 'other'."""
    if not head:
        return "other"
    key = head.strip().lower()
    key = re.sub(r"^\d+(\.\d+)*\s*[.)]?\s*", "", key)   # strip leading numbering "3.1 "
    if key in label_map:
        return label_map[key]
    for k, v in label_map.items():
        if key.startswith(k):
            return v
    return "other"


def is_dropped_head(head: str, drop_keywords) -> bool:
    if not head:
        return False
    low = head.strip().lower()
    return any(kw in low for kw in drop_keywords)


# ---- main parse ---------------------------------------------------------------

def parse_tei(xml_str: str, drop_keywords, label_map) -> ParsedDoc:
    """Parse a GROBID TEI string into a ParsedDoc under the KEEP/DROP policy."""
    # ElementTree chokes on a leading XML declaration with encoding sometimes; feed str.
    root = ET.fromstring(xml_str)
    doc = ParsedDoc()

    # Title (kept as metadata).
    t = root.find(".//tei:teiHeader//tei:titleStmt/tei:title", NS)
    if t is not None:
        doc.title = _text_of(t)

    # DOI recorded by GROBID (cross-check only; the canonical DOI comes from the filename).
    for idno in root.findall(".//tei:teiHeader//tei:idno", NS):
        if (idno.get("type") or "").upper() == "DOI" and idno.text:
            doc.tei_doi = idno.text.strip()
            break

    # Abstract (kept as content).
    abs = root.find(".//tei:profileDesc/tei:abstract", NS)
    if abs is not None:
        paras = [_text_of(p) for p in abs.findall(".//tei:p", NS)]
        doc.abstract = _clean(" ".join(x for x in paras if x))

    body = root.find(".//tei:text/tei:body", NS)
    if body is not None:
        # Sections: every <div> that carries its OWN direct <p> paragraphs becomes a
        # unit labelled by its nearest <head>. Iterating direct-child <p> only means a
        # paragraph belongs to exactly one unit (no duplication across nested divs), and
        # each unit stays within a single section (never straddles).
        for div in body.iter(f"{{{TEI_NS}}}div"):
            head_el = div.find(f"{{{TEI_NS}}}head")
            head = _text_of(head_el) if head_el is not None else ""
            if is_dropped_head(head, drop_keywords):
                doc.dropped_heads.append(head)
                continue
            paras = [
                _text_of(p) for p in list(div)
                if p.tag == f"{{{TEI_NS}}}p"
            ]
            body_text = _clean(" ".join(x for x in paras if x))
            if not body_text:
                continue
            doc.sections.append(Section(
                label=canonical_label(head, label_map),
                head=head,
                text=body_text,
            ))

        # Captions: every <figure> (type="table" -> table caption) contributes its
        # <figDesc> text only. Table grids are intentionally not reconstructed.
        for fig in body.iter(f"{{{TEI_NS}}}figure"):
            kind = "table" if (fig.get("type") == "table") else "figure"
            desc = fig.find(f"{{{TEI_NS}}}figDesc")
            cap = _text_of(desc) if desc is not None else ""
            if cap:
                doc.captions.append(Caption(kind=kind, text=cap))

    return doc
