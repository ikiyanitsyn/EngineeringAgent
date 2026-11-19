import shutil
import subprocess

import pytest

from engagent import cadinput, drawings


def test_attachment_links_are_split_between_cad_and_drawings(tmp_path):
    text = ("see https://github.com/user-attachments/files/123/bracket.pdf and "
            "https://github.com/user-attachments/files/124/part.step.txt and "
            "![d](https://github.com/user-attachments/assets/0123abcd-0123-4567-89ab-0123456789ab)")
    assert drawings.find(text, tmp_path)["urls"] == [
        "https://github.com/user-attachments/files/123/bracket.pdf",
        "https://github.com/user-attachments/assets/0123abcd-0123-4567-89ab-0123456789ab"]
    assert cadinput.find_inputs(text, tmp_path)["urls"] == ["https://github.com/user-attachments/files/124/part.step.txt"]


def test_repository_paths_and_file_kinds(tmp_path):
    (tmp_path / "inbox").mkdir()
    (tmp_path / "inbox" / "d.png").write_bytes(b"\x89PNG\r\n\x1a\nxx")
    f = drawings.find("drawing at inbox/d.png, missing.pdf", tmp_path)
    assert [p.name for p in f["paths"]] == ["d.png"]
    assert drawings.kind(b"%PDF-1.7") == "pdf" and drawings.kind(b"<html>") is None
    imgs, problems = drawings.collect(["inbox/d.png"], tmp_path)
    assert len(imgs) == 1 and not problems


@pytest.mark.skipif(not shutil.which("pdftoppm"), reason="poppler not installed")
def test_pdf_pages_are_rendered(tmp_path):
    pdf = (b"%PDF-1.4\n1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj 2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>"
           b"endobj 3 0 obj<</Type/Page/Parent 2 0 R/MediaBox[0 0 1191 842]>>endobj\ntrailer<</Root 1 0 R>>\n%%EOF")
    out = drawings.pages(pdf)                          # an A3 landscape sheet
    assert len(out) == 1 and drawings.kind(out[0]) == "png"
