import base64
import io
import zipfile

import pytest
from defusedxml.common import DefusedXmlException
from fastapi import HTTPException
from PIL import Image

from plateforme.document_worker import parse
from plateforme.documents import extraire


def archive(files):
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w") as zipped:
        for name, body in files.items():
            zipped.writestr(name, body)
    return output.getvalue()


def test_word_and_powerpoint_follow_document_order():
    document = archive(
        {
            "word/document.xml": "<document><p><r><t>First paragraph.</t></r></p><p><r><t>Second paragraph.</t></r></p></document>"
        }
    )
    assert parse(document, ".docx")["text"] == "First paragraph.\nSecond paragraph."
    slides = archive(
        {
            "ppt/presentation.xml": '<presentation xmlns:r="urn:relationships"><sldIdLst><sldId r:id="second"/><sldId r:id="first"/></sldIdLst></presentation>',
            "ppt/_rels/presentation.xml.rels": '<Relationships><Relationship Id="first" Target="slides/slide1.xml"/><Relationship Id="second" Target="slides/slide2.xml"/></Relationships>',
            "ppt/slides/slide1.xml": "<slide><t>Last in presentation</t></slide>",
            "ppt/slides/slide2.xml": "<slide><t>First in presentation</t></slide>",
        }
    )
    assert (
        parse(slides, ".pptx")["text"]
        == "[Slide 1]\nFirst in presentation\n\n[Slide 2]\nLast in presentation"
    )


def workbook():
    return {
        "xl/workbook.xml": '<workbook xmlns:r="urn:relationships"><sheets><sheet name="Costs" r:id="r2"/><sheet name="Services" r:id="r1"/></sheets></workbook>',
        "xl/_rels/workbook.xml.rels": '<Relationships><Relationship Id="r1" Target="worksheets/sheet1.xml"/><Relationship Id="r2" Target="/xl/worksheets/sheet2.xml"/></Relationships>',
        "xl/sharedStrings.xml": "<sst><si><t>Gateway</t></si></sst>",
        "xl/worksheets/sheet1.xml": '<worksheet><sheetData><row><c r="A1" t="s"><v>0</v></c></row></sheetData></worksheet>',
        "xl/worksheets/sheet2.xml": '<worksheet><sheetData><row><c r="B2"><f>40+2</f><v>42</v></c></row></sheetData></worksheet>',
    }


def test_excel_labels_cells_and_cached_formula_values_are_accurate():
    text = parse(archive(workbook()), ".xlsx")["text"]
    assert (
        text.index("Costs")
        < text.index("B2=42 [cached formula value]")
        < text.index("Services")
        < text.index("A1=Gateway")
    )
    assert "40+2" not in text and "not recalculated" in text


@pytest.mark.parametrize(
    "target", ["../../outside.xml", "https://example.com/secret", "file:///etc/passwd"]
)
def test_external_or_traversing_workbook_relationship_is_rejected(target):
    files = workbook()
    files["xl/_rels/workbook.xml.rels"] = (
        f'<Relationships><Relationship Id="r2" Target="{target}"/></Relationships>'
    )
    with pytest.raises(ValueError):
        parse(archive(files), ".xlsx")


@pytest.mark.parametrize(
    "name,body",
    [
        ("../bad.xml", "x"),
        ("word/vbaProject.bin", "x"),
        (
            "word/document.xml",
            '<!DOCTYPE doc [<!ENTITY secret SYSTEM "file:///etc/passwd">]><doc>&secret;</doc>',
        ),
    ],
)
def test_office_rejects_traversal_macros_and_entities(name, body):
    with pytest.raises((ValueError, DefusedXmlException)):
        parse(archive({name: body}), ".docx")


def test_compression_bomb_rejected_before_xml_parsing():
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as zipped:
        zipped.writestr("word/document.xml", "x" * 2_000_000)
    with pytest.raises(ValueError, match="expansion"):
        parse(output.getvalue(), ".docx")


def test_image_normalized_without_metadata_and_dimensions_bounded():
    source = Image.new("RGB", (2400, 1200), color="navy")
    output = io.BytesIO()
    source.save(output, "JPEG", comment=b"PRIVATE_METADATA")
    result = parse(output.getvalue(), ".jpg")
    assert result["width"] == 1600 and result["height"] == 800
    normalized = base64.b64decode(result["image"])
    assert b"PRIVATE_METADATA" not in normalized
    with Image.open(io.BytesIO(normalized)) as image:
        assert image.format == "JPEG" and not image.getexif()


def test_text_truncation_and_binary_refusal_are_explicit():
    result = parse(("é" * 17000).encode(), ".csv")
    assert len(result["text"]) == 16000 and result["truncated"]
    with pytest.raises(ValueError):
        parse(b"hello\x00hidden", ".txt")


@pytest.mark.asyncio
async def test_real_worker_handles_office_and_rejects_malicious_xml():
    result = await extraire("costs.xlsx", base64.b64encode(archive(workbook())).decode())
    assert "B2=42" in result["text"]
    with pytest.raises(HTTPException) as error:
        await extraire(
            "unsafe.docx",
            base64.b64encode(
                archive(
                    {
                        "word/document.xml": '<!DOCTYPE doc [<!ENTITY secret SYSTEM "file:///etc/passwd">]><doc>&secret;</doc>'
                    }
                )
            ).decode(),
        )
    assert error.value.status_code == 422
    assert "passwd" not in error.value.detail
