"""Phase 1A format isolation and minimal Flat OPC, promoted without experiment imports."""
from copy import deepcopy
from . import stdlib_xml as etree
from . import template_core as phase0
W, NS = phase0.W, phase0.NS
PKG = "http://schemas.microsoft.com/office/2006/xmlPackage"
REL = "http://schemas.openxmlformats.org/package/2006/relationships"
def OxmlElement(tag):
    return etree.Element("{" + W + "}" + tag.split(":")[1])

def _merge_properties(*layers):
    """Materialize this audited template's inherited properties on the carrier.

    Does not change Phase 0. Explicit paragraph/run properties win. Template
    has no named paragraph/table style use beyond the defaults audited in P0.
    """
    merged = {}
    for layer in layers:
        if layer is None:
            continue
        for child in layer:
            if child.tag in merged:
                current = merged[child.tag]
                current.attrib.update(child.attrib)
            else:
                merged[child.tag] = deepcopy(child)
    return list(merged.values())

def _replace_props(node, name, layers):
    old = node.find(f"w:{name}", NS)
    replacement = OxmlElement(f"w:{name}")
    children = _merge_properties(*layers)
    if name == "rPr":
        order = ["rStyle", "rFonts", "b", "bCs", "i", "iCs", "caps", "smallCaps", "strike",
                 "dstrike", "outline", "shadow", "emboss", "imprint", "noProof", "snapToGrid",
                 "vanish", "webHidden", "color", "spacing", "w", "kern", "position", "sz",
                 "szCs", "highlight", "u", "effect", "bdr", "shd", "fitText", "vertAlign",
                 "rtl", "cs", "em", "lang", "eastAsianLayout", "specVanish", "oMath"]
        rank = {f"{{{W}}}{tag}": index for index, tag in enumerate(order)}
        children.sort(key=lambda n: rank.get(n.tag, len(rank)))
    for child in children:
        replacement.append(child)
    fonts = replacement.find("w:rFonts", NS)
    if fonts is not None:
        for attr, theme in (("ascii", "asciiTheme"), ("hAnsi", "hAnsiTheme"),
                            ("eastAsia", "eastAsiaTheme"), ("cs", "cstheme")):
            if f"{{{W}}}{attr}" in fonts.attrib:
                fonts.attrib.pop(f"{{{W}}}{theme}", None)
    if old is not None:
        node.replace(old, replacement)
    else:
        node.insert(0, replacement)
    return replacement

def freeze_inherited_format(table, styles_xml):
    """Add equivalent direct formatting so host Normal/themes cannot override.

    Original table/row/cell geometry is deep copied. Only inherited defaults
    are made explicit on an independent insertion carrier, not the template.
    """
    table = deepcopy(table)
    styles = phase0.parse_xml(styles_xml)
    normal = next(s for s in styles.findall("w:style", NS)
                  if s.get(f"{{{W}}}type") == "paragraph" and s.get(f"{{{W}}}default") == "1")
    default_r = styles.find("w:docDefaults/w:rPrDefault/w:rPr", NS)
    normal_r = normal.find("w:rPr", NS)
    normal_p = normal.find("w:pPr", NS)
    # OOXML's absent character properties must not inherit host Normal either.
    base_r = OxmlElement("w:rPr")
    for tag, value in (("b", "0"), ("bCs", "0"), ("i", "0"), ("iCs", "0"),
                       ("strike", "0"), ("dstrike", "0"), ("caps", "0"),
                       ("smallCaps", "0"), ("vanish", "0"), ("color", "auto"),
                       ("u", "none"), ("vertAlign", "baseline")):
        child = OxmlElement(f"w:{tag}")
        child.set(f"{{{W}}}val", value)
        base_r.append(child)
    for p in table.findall(".//w:p", NS):
        direct_p = p.find("w:pPr", NS)
        mark_r = deepcopy(direct_p.find("w:rPr", NS)) if direct_p is not None else None
        props = _replace_props(p, "pPr", [normal_p, direct_p])
        # pPr.rPr must remain after paragraph properties.
        mark = props.find("w:rPr", NS)
        if mark is not None:
            props.remove(mark)
        for tag, attributes in (("spacing", {"before": "0", "after": "0", "line": "240", "lineRule": "auto"}),):
            if props.find(f"w:{tag}", NS) is None:
                n = OxmlElement(f"w:{tag}")
                for key, value in attributes.items():
                    n.set(f"{{{W}}}{key}", value)
                # spacing precedes jc in pPr.
                jc = props.find("w:jc", NS)
                if jc is not None:
                    jc.addprevious(n)
                else:
                    props.append(n)
        mark_holder = etree.Element(f"{{{W}}}p")
        resolved_mark = _replace_props(mark_holder, "rPr", [base_r, default_r, normal_r, mark_r])
        props.append(resolved_mark)
        for run in p.findall("w:r", NS):
            _replace_props(run, "rPr", [base_r, default_r, normal_r, mark_r, run.find("w:rPr", NS)])
        # Word assigns fresh identities in destination; no clone identity collision.
        for key in list(p.attrib):
            if key.endswith(("}paraId", "}textId")):
                del p.attrib[key]
    default_table = next(s for s in styles.findall("w:style", NS)
                         if s.get(f"{{{W}}}type") == "table" and s.get(f"{{{W}}}default") == "1")
    props = table.find("w:tblPr", NS)
    for tag in ("tblInd", "tblCellMar"):
        child = default_table.find(f"w:tblPr/w:{tag}", NS)
        if child is not None and props.find(f"w:{tag}", NS) is None:
            anchor = props.find("w:tblBorders", NS) if tag == "tblInd" else props.find("w:tblLayout", NS)
            if anchor is not None:
                anchor.addprevious(deepcopy(child))
            else:
                props.append(deepcopy(child))
    return table

def flat_package(nodes):
    """Minimal Flat OPC: no styles/theme/settings/section/header/footer part."""
    package = etree.Element(f"{{{PKG}}}package", nsmap={"pkg": PKG})
    relationships = etree.Element(f"{{{REL}}}Relationships", nsmap={None: REL})
    rel = etree.SubElement(relationships, f"{{{REL}}}Relationship")
    rel.attrib.update({"Id": "rId1", "Type": "http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument",
                       "Target": "word/document.xml"})
    document = etree.Element(f"{{{W}}}document", nsmap={"w": W})
    body = etree.SubElement(document, f"{{{W}}}body")
    for node in nodes:
        body.append(deepcopy(node))
    for name, content_type, xml in (
        ("/_rels/.rels", "application/vnd.openxmlformats-package.relationships+xml", relationships),
        ("/word/document.xml", "application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml", document),
    ):
        part = etree.SubElement(package, f"{{{PKG}}}part")
        part.set(f"{{{PKG}}}name", name)
        part.set(f"{{{PKG}}}contentType", content_type)
        etree.SubElement(part, f"{{{PKG}}}xmlData").append(xml)
    return etree.tostring(package, encoding="unicode")

def ending_paragraph():
    # A real paragraph after a table is the outside-cell insertion anchor.
    return etree.Element(f"{{{W}}}p", nsmap={"w": W})


def fit_table_to_available_width(table, available_points):
    """Shrink widths only, with cumulative rounding and coherent merged tcW."""
    import math
    if not math.isfinite(available_points) or available_points <= 0:
        raise ValueError('Word 页面可用宽度无效')
    result = deepcopy(table)
    columns = result.findall('w:tblGrid/w:gridCol', NS)
    widths = [int(col.get(f'{{{W}}}w')) for col in columns]
    original = sum(widths)
    target = int(round(available_points * 20))
    if target >= original:
        return result
    if target < len(columns):
        raise ValueError('Word 页面过窄，无法容纳人员表')
    accumulated = 0
    boundaries = [0]
    for width in widths:
        accumulated += width
        boundaries.append(round(accumulated * target / original))
    scaled = [b-a for a, b in zip(boundaries, boundaries[1:])]
    if min(scaled) <= 0:
        raise ValueError('Word 页面过窄，表格列宽无效')
    for col, width in zip(columns, scaled):
        col.set(f'{{{W}}}w', str(width))
    result.find('w:tblPr/w:tblW', NS).set(f'{{{W}}}w', str(target))
    for row in result.findall('w:tr', NS):
        index = 0
        for cell in row.findall('w:tc', NS):
            span = cell.find('w:tcPr/w:gridSpan', NS)
            span = int(span.get(f'{{{W}}}val')) if span is not None else 1
            cell.find('w:tcPr/w:tcW', NS).set(f'{{{W}}}w', str(sum(scaled[index:index+span])))
            index += span
        if index != len(columns):
            raise ValueError('人员表合并单元格与列网格不一致')
    return result
