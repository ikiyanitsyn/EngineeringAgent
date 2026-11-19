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


def test_private_attachment_falls_back_to_the_signed_link():
    import threading
    from http.server import BaseHTTPRequestHandler, HTTPServer

    class H(BaseHTTPRequestHandler):
        def do_GET(self):
            if "jwt=" in self.path:
                self.send_response(200); self.end_headers(); self.wfile.write(b"%PDF-1.4 drawing")
            else:                                     # what a private repository gives a bot: a login page
                self.send_response(200); self.end_headers(); self.wfile.write(b"<!DOCTYPE html><html>login")

        def log_message(self, *a):
            pass

    srv = HTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    uid = "0123abcd-0123-4567-89ab-0123456789ab"
    base = f"http://127.0.0.1:{srv.server_port}"
    html = f'<img src="https://private-user-images.githubusercontent.com/1/2-{uid}.png?jwt=abc&amp;x=1">'
    alt = drawings.signed_alternates([html])
    assert alt[uid].endswith("jwt=abc&x=1")
    alt[uid] = f"{base}/signed/{uid}?jwt=abc"             # point the signed link at the fake server
    try:
        assert drawings.download(f"{base}/user-attachments/assets/{uid}", "tok", alt).startswith(b"%PDF")
        with pytest.raises(ValueError, match="inbox/"):
            drawings.download(f"{base}/user-attachments/assets/ffffffff-0123-4567-89ab-0123456789ab", "tok", alt)
    finally:
        srv.shutdown()


def test_step_from_a_share_link(tmp_path):
    import threading
    from http.server import BaseHTTPRequestHandler, HTTPServer
    seen = []

    class H(BaseHTTPRequestHandler):
        def do_GET(self):
            seen.append(self.path)
            ok = "dl=1" in self.path
            self.send_response(200); self.end_headers()
            self.wfile.write(b"ISO-10303-21;\nHEADER;" if ok else b"<!DOCTYPE html><html>preview")

        def log_message(self, *a):
            pass

    srv = HTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    try:
        # a Dropbox-style link: the preview page unless dl=1
        url = f"http://127.0.0.1:{srv.server_port}/dropbox.com/s/x/bracket.step?dl=0"
        got = cadinput.fetch(url, tmp_path, None)
        assert got[0].name == "bracket.step" and seen[-1].endswith("dl=1")
    finally:
        srv.shutdown()
    assert cadinput.direct_link("https://drive.google.com/file/d/AbC-1_x/view?usp=sharing") == \
        "https://drive.google.com/uc?export=download&id=AbC-1_x"


def test_many_parts_ask_which_unless_named(tmp_path):
    from pathlib import Path
    parts = [Path(f"nist_ctc_0{i}_ap203.step") for i in range(1, 7)]
    got, q = cadinput.choose_parts(parts, "check my parts")
    assert not got and cadinput.PICK_MARK in q and "`nist_ctc_01_ap203`" in q
    got, q = cadinput.choose_parts(parts, "use nist_ctc_03_ap203 please")
    assert [p.stem for p in got] == ["nist_ctc_03_ap203"] and q is None
    assert cadinput.choose_parts(parts[:2], "x") == (parts[:2], None)
