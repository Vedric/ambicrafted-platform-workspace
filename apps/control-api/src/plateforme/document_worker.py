"""Private stdin/stdout parser. No macros, code, external links or shell execution.

Linux/macOS impose CPU/address-space limits in addition to the parent's deadline.
This is process isolation and resource limiting, not an OS security sandbox.
"""

import base64
import io
import json
import re
import sys
import warnings
import zipfile
from pathlib import PurePosixPath

MAX_TEXT = 16_000
MAX_XML = 8 * 1024 * 1024


def xml(data: bytes):
    from defusedxml.ElementTree import fromstring

    return fromstring(data, forbid_dtd=True, forbid_entities=True, forbid_external=True)


def local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def office(data: bytes, extension: str) -> str:
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        infos = archive.infolist()
        if len(infos) > 2000 or sum(item.file_size for item in infos) > 32 * 1024 * 1024:
            raise ValueError("Archive limits")
        for item in infos:
            path = PurePosixPath(item.filename)
            if (
                path.is_absolute()
                or ".." in path.parts
                or "\\" in item.filename
                or item.flag_bits & 1
            ):
                raise ValueError("Unsafe archive member")
            if item.file_size > MAX_XML or item.file_size > max(100, item.compress_size) * 100:
                raise ValueError("Archive expansion limit")
            if (
                "vbaproject" in item.filename.lower()
                or (item.external_attr >> 16) & 0o170000 == 0o120000
            ):
                raise ValueError("Macros and symlinks are unsupported")
        names = {item.filename for item in infos}
        if len(names) != len(infos):
            raise ValueError("Duplicate archive member")

        def read(name: str):
            return xml(archive.read(name))

        def relationships(part: str, root):
            directory, filename = part.rsplit("/", 1)
            relation_file = f"{directory}/_rels/{filename}.rels"
            relations = {}
            for relation in read(relation_file):
                target = relation.attrib.get("Target", "")
                if relation.attrib.get("TargetMode", "Internal") != "Internal":
                    continue  # External hyperlinks are source data, never fetched.
                path = PurePosixPath(target)
                if ".." in path.parts or "\\" in target or ":" in target:
                    continue
                name = target.lstrip("/") if target.startswith("/") else f"{directory}/{target}"
                relations[relation.attrib.get("Id", "")] = name
            for node in root.iter():
                if local(node.tag) not in {"sheet", "sldId"}:
                    continue
                relation_id = next(
                    (value for key, value in node.attrib.items() if key.endswith("}id")), None
                )
                target = relations.get(relation_id)
                if target not in names:
                    raise ValueError("Missing or external Office relationship")
                yield node, target

        if extension == ".docx":
            root = read("word/document.xml")
            return "\n".join(
                "".join(node.text or "" for node in paragraph.iter() if local(node.tag) == "t")
                for paragraph in root.iter()
                if local(paragraph.tag) == "p"
            )
        if extension == ".pptx":
            presentation = read("ppt/presentation.xml")
            slides = [target for _, target in relationships("ppt/presentation.xml", presentation)]
            if any(not re.fullmatch(r"ppt/slides/slide\d+\.xml", name) for name in slides):
                raise ValueError("Invalid slide relationship")
            return "\n\n".join(
                f"[Slide {index + 1}]\n"
                + "\n".join(node.text or "" for node in read(name).iter() if local(node.tag) == "t")
                for index, name in enumerate(slides)
            )
        workbook = read("xl/workbook.xml")
        shared = []
        if "xl/sharedStrings.xml" in names:
            shared = [
                "".join(node.text or "" for node in item.iter() if local(node.tag) == "t")
                for item in read("xl/sharedStrings.xml").iter()
                if local(item.tag) == "si"
            ]
        output = ["[Stored cell values only; formulas are not recalculated.]"]
        for sheet, name in relationships("xl/workbook.xml", workbook):
            if not re.fullmatch(r"xl/worksheets/[^/]+\.xml", name):
                raise ValueError("Invalid sheet relationship")
            output.append(f"[Sheet: {sheet.attrib.get('name', 'Sheet')}; {name}]")
            for row in read(name).iter():
                if local(row.tag) != "row":
                    continue
                cells = []
                for cell in row:
                    if local(cell.tag) != "c":
                        continue
                    values = [
                        node.text or "" for node in cell.iter() if local(node.tag) in {"v", "t"}
                    ]
                    value = " ".join(values)
                    if cell.attrib.get("t") == "s":
                        value = (
                            shared[int(value)]
                            if value.isdigit() and int(value) < len(shared)
                            else "[Missing shared string]"
                        )
                    if any(local(node.tag) == "f" for node in cell):
                        value += " [cached formula value]"
                    cells.append(cell.attrib.get("r", "?") + "=" + value)
                output.append(" | ".join(cells))
        return "\n".join(output)


def parse(data: bytes, extension: str) -> dict:
    if extension in {".png", ".jpg", ".jpeg", ".webp"}:
        from PIL import Image, ImageOps

        Image.MAX_IMAGE_PIXELS = 12_000_000
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(io.BytesIO(data)) as source:
                if (
                    source.format not in {"PNG", "JPEG", "WEBP"}
                    or source.width * source.height > 12_000_000
                ):
                    raise ValueError("Unsupported or oversized image")
                source.seek(0)
                image = ImageOps.exif_transpose(source).convert("RGB")
                image.thumbnail((1600, 1600))
                image.info.clear()  # Pillow can otherwise carry JPEG comments into the output.
                output = io.BytesIO()
                image.save(output, format="JPEG", quality=85, optimize=True)
                if output.tell() > 1_000_000:
                    raise ValueError("Normalized image is too large")
                return {
                    "kind": "image",
                    "text": "",
                    "image": base64.b64encode(output.getvalue()).decode("ascii"),
                    "truncated": getattr(source, "n_frames", 1) > 1,
                    "width": image.width,
                    "height": image.height,
                }
    if extension in {".docx", ".xlsx", ".pptx"}:
        text = office(data, extension)
    elif extension == ".pdf":
        from pypdf import PdfReader

        if not data.startswith(b"%PDF-"):
            raise ValueError("Invalid PDF signature")
        pdf = PdfReader(io.BytesIO(data), strict=True)
        if pdf.is_encrypted or len(pdf.pages) > 100:
            raise ValueError("Encrypted or oversized PDF")
        pages = [page.extract_text() or "" for page in pdf.pages]
        text = "\n\n".join(f"[Page {index + 1}]\n" + page for index, page in enumerate(pages))
        if not any(page.strip() for page in pages):
            raise ValueError("Scanned PDFs need image export")
    else:
        text = data.decode("utf-8-sig")
        if "\x00" in text:
            raise ValueError("Binary content is not UTF-8 text")
    text = "".join(char for char in text if ord(char) >= 32 or char in "\n\t\r")
    if not text.strip():
        raise ValueError("Empty extracted text")
    return {"kind": "text", "text": text[:MAX_TEXT], "truncated": len(text) > MAX_TEXT}


def main():
    try:
        import resource

        resource.setrlimit(resource.RLIMIT_AS, (1024**3, 1024**3))
        resource.setrlimit(resource.RLIMIT_CPU, (12, 12))
        resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    except ImportError:
        pass  # The parent still enforces its deadline on Windows.

    def deny(event, args):
        if event in {
            "socket.connect",
            "socket.bind",
            "subprocess.Popen",
            "os.system",
            "os.exec",
            "os.posix_spawn",
        }:
            raise PermissionError("Parser network and execution are disabled")

    sys.addaudithook(deny)
    data = sys.stdin.buffer.read(8 * 1024 * 1024 + 1)
    if not data or len(data) > 8 * 1024 * 1024:
        raise ValueError("File size limit")
    print(json.dumps(parse(data, sys.argv[1]), ensure_ascii=False))


if __name__ == "__main__":
    try:
        main()
    except Exception:  # noqa: BLE001 — parser boundary emits no document bytes or traceback.
        raise SystemExit(2) from None
