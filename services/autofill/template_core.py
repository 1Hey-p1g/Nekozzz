"""Promoted Phase 0 audited addresses and XML primitives; original experiments remain unchanged."""
from copy import deepcopy
from dataclasses import dataclass
import hashlib
from io import BytesIO
from pathlib import Path
from zipfile import ZipFile
from . import stdlib_xml as etree

W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"

W14 = "http://schemas.microsoft.com/office/word/2010/wordml"

NS = {"w": W, "w14": W14}

XML_SPACE = "{http://www.w3.org/XML/1998/namespace}space"

CAPACITY = 3

TEMPLATE_SHA256 = "892ae87bd316d82448cbd297938359417b7a08650f3d40f6c3b182a803119a52"

@dataclass(frozen=True)
class PersonTableData:
    name: str
    gender: str
    age: int
    school: str
    major: str
    title: str
    registration: str
    role: str
    performance: str

@dataclass(frozen=True)
class PersonRecordBlock:
    """Zero-based XML rows/tc, NOT python-docx's expanded grid cell indexes."""
    slot: int
    first_row: int

    def targets(self):
        r = self.first_row
        return {
            "name": (r, 1), "gender": (r, 3), "age": (r, 5),
            "school": (r + 1, 1), "major": (r + 1, 3), "title": (r + 1, 5),
            "registration": (r + 2, 1), "role": (r + 2, 3),
            "performance": (r + 4, 0),
        }

BLOCKS = tuple(PersonRecordBlock(i, i * 5) for i in range(CAPACITY))

VALUE_ADDRESSES = {address for block in BLOCKS for address in block.targets().values()}

def parse_xml(payload: bytes):
    return etree.fromstring(payload, etree.XMLParser(resolve_entities=False, no_network=True))

def cell_at(table, address):
    row, cell = address
    return table.findall("w:tr", NS)[row].findall("w:tc", NS)[cell]

def value_text(cell):
    fragments = []
    for node in cell.iter():
        if node.tag == f"{{{W}}}t":
            fragments.append(node.text or "")
        elif node.tag == f"{{{W}}}br":
            fragments.append("\n")
        elif node.tag == f"{{{W}}}tab":
            fragments.append("\t")
    return "".join(fragments)

def canonical(node):
    # Ignore unused namespaces inherited from ancestors, not element properties.
    return etree.tostring(node, method="c14n", exclusive=True)

def load_template(template: Path):
    """Fail closed: these mappings apply only to the supplied audited file."""
    data = template.read_bytes()
    if hashlib.sha256(data).hexdigest() != TEMPLATE_SHA256:
        raise ValueError("Template differs from the audited personnel DOCX; re-audit required")
    with ZipFile(BytesIO(data)) as archive:
        root = parse_xml(archive.read("word/document.xml"))
    body = root.find("w:body", NS)
    tables = body.findall("w:tbl", NS)
    if len(tables) != 1 or len(root.findall(".//w:tbl", NS)) != 1:
        raise ValueError("Expected exactly one top-level personnel table")
    table = tables[0]
    rows = table.findall("w:tr", NS)
    if len(rows) != 15 or len(table.findall("w:tblGrid/w:gridCol", NS)) != 8:
        raise ValueError("Unexpected personnel table layout")
    if table.findall('.//w:vMerge', NS):
        raise ValueError('Unexpected vertical cell merge')
    expected_spans = ([1, 2, 1, 2, 1, 1], [1, 2, 1, 2, 1, 1], [2, 3, 1, 2], [8], [8])
    for index, row in enumerate(rows):
        spans = [int(span.get(f'{{{W}}}val')) if (span := cell.find('w:tcPr/w:gridSpan', NS)) is not None
                 else 1 for cell in row.findall('w:tc', NS)]
        if spans != expected_spans[index % 5]:
            raise ValueError('Unexpected horizontal cell merge')
    labels = [(0, 0, "姓名"), (0, 2, "性别"), (0, 4, "年龄"),
              (1, 0, "毕业学校"), (1, 2, "所学专业"), (1, 4, "职称"),
              (2, 0, "注册名称及证书编号"), (2, 2, "拟担任的工作"),
              (3, 0, "近年来同类工程的主要工作业绩及担任的主要工作")]
    for block in BLOCKS:
        if [len(row.findall("w:tc", NS)) for row in rows[block.first_row:block.first_row+5]] != [6, 6, 4, 1, 1]:
            raise ValueError("Unexpected record block cell count")
        for row, tc, label in labels:
            if value_text(cell_at(table, (block.first_row + row, tc))) != label:
                raise ValueError("Fixed label differs from audited mapping")
        for address in block.targets().values():
            cell = cell_at(table, address)
            if value_text(cell) or len(cell.findall("w:p", NS)) != 1:
                raise ValueError("Expected one empty value paragraph")
    return data, root, body, table

def replace_target_text_preserving_format(cell, text: str):
    """Fill an audited EMPTY value paragraph; preserve tcPr/pPr/existing rPr.

    No cell.text assignment, no deletion of labels or formatting. In the real
    template all value slots have pPr/rPr but no run. Copy that paragraph-mark
    rPr to a minimal run. Newlines become w:br in that same paragraph.
    """
    paragraphs = cell.findall("w:p", NS)
    if len(paragraphs) != 1 or value_text(cell):
        raise ValueError("Refusing to overwrite a non-empty or multi-paragraph value cell")
    p = paragraphs[0]
    runs = p.findall("w:r", NS)
    if any(child.tag not in (f"{{{W}}}pPr", f"{{{W}}}r") for child in p):
        raise ValueError("Unsupported content in value paragraph")
    if runs:
        run = runs[0]
        if any(child.tag != f"{{{W}}}rPr" for r in runs for child in r):
            raise ValueError("Unsupported content in existing empty run")
    else:
        run = etree.SubElement(p, f"{{{W}}}r")
        formatting = p.find("w:pPr/w:rPr", NS)
        if formatting is not None:
            run.append(deepcopy(formatting))
    for line_index, line in enumerate(text.split("\n")):
        if line_index:
            etree.SubElement(run, f"{{{W}}}br")
        for tab_index, part in enumerate(line.split("\t")):
            if tab_index:
                etree.SubElement(run, f"{{{W}}}tab")
            node = etree.SubElement(run, f"{{{W}}}t")
            node.set(XML_SPACE, "preserve")
            node.text = part
