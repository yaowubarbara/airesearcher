#!/usr/bin/env python3
"""Simple upload server for book photos."""
import os
import json
import cgi
import html
import urllib.parse
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path
from datetime import datetime

UPLOAD_DIR = Path(__file__).parent / "book_photos"
UPLOAD_DIR.mkdir(exist_ok=True)

HTML_PAGE = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Book Photo Upload</title>
<style>
* { box-sizing: border-box; margin: 0; padding: 0; }
body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', 'Noto Sans SC', sans-serif; background: #0f172a; color: #e2e8f0; padding: 2rem; max-width: 900px; margin: 0 auto; }
h1 { font-size: 1.6rem; color: #f8fafc; margin-bottom: 0.3rem; }
.subtitle { color: #94a3b8; font-size: 0.9rem; margin-bottom: 2rem; }
.drop-zone { border: 2px dashed #475569; border-radius: 16px; padding: 3rem 2rem; text-align: center; transition: all 0.2s; cursor: pointer; background: #1e293b; margin-bottom: 2rem; }
.drop-zone:hover, .drop-zone.drag-over { border-color: #6366f1; background: #1e1b4b; }
.drop-zone h2 { color: #c4b5fd; font-size: 1.2rem; margin-bottom: 0.5rem; }
.drop-zone p { color: #64748b; font-size: 0.85rem; }
.drop-zone input { display: none; }
.btn { display: inline-block; background: #6366f1; color: white; padding: 0.6rem 1.5rem; border-radius: 8px; border: none; font-size: 0.9rem; cursor: pointer; font-weight: 600; margin-top: 1rem; }
.btn:hover { background: #4f46e5; }
.progress { display: none; margin: 1rem 0; }
.progress-bar { height: 6px; background: #334155; border-radius: 3px; overflow: hidden; }
.progress-fill { height: 100%; background: #6366f1; border-radius: 3px; transition: width 0.3s; width: 0%; }
.progress-text { font-size: 0.8rem; color: #94a3b8; margin-top: 0.3rem; }
.gallery { display: grid; grid-template-columns: repeat(auto-fill, minmax(200px, 1fr)); gap: 1rem; }
.gallery-item { background: #1e293b; border-radius: 12px; overflow: hidden; border: 1px solid #334155; transition: border-color 0.2s; }
.gallery-item:hover { border-color: #6366f1; }
.gallery-item img { width: 100%; height: 180px; object-fit: cover; cursor: pointer; }
.gallery-item .info { padding: 0.6rem 0.8rem; }
.gallery-item .name { font-size: 0.8rem; color: #e2e8f0; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.gallery-item .meta { font-size: 0.7rem; color: #64748b; margin-top: 0.2rem; }
.gallery-item .delete-btn { font-size: 0.7rem; color: #f87171; cursor: pointer; float: right; }
.gallery-item .delete-btn:hover { text-decoration: underline; }
.count { font-size: 0.9rem; color: #94a3b8; margin-bottom: 1rem; }
.toast { position: fixed; top: 1rem; right: 1rem; background: #065f46; color: #6ee7b7; padding: 0.8rem 1.2rem; border-radius: 8px; font-size: 0.85rem; display: none; z-index: 100; animation: fadeIn 0.3s; }
@keyframes fadeIn { from { opacity: 0; transform: translateY(-10px); } to { opacity: 1; transform: translateY(0); } }
.modal { display: none; position: fixed; top: 0; left: 0; width: 100%; height: 100%; background: rgba(0,0,0,0.9); z-index: 50; justify-content: center; align-items: center; }
.modal.active { display: flex; }
.modal img { max-width: 95%; max-height: 95%; object-fit: contain; }
.modal-close { position: fixed; top: 1rem; right: 1.5rem; color: white; font-size: 2rem; cursor: pointer; z-index: 51; }
</style>
</head>
<body>
<h1>Book Photo Upload</h1>
<p class="subtitle">Upload book page photos for Claude to read and analyze</p>

<div class="drop-zone" id="dropZone">
    <h2>Drop photos here</h2>
    <p>or click to select files (JPG, PNG, HEIC, PDF)</p>
    <input type="file" id="fileInput" multiple accept="image/*,.pdf,.heic">
    <br><button class="btn" onclick="document.getElementById('fileInput').click()">Select Files</button>
</div>

<div class="progress" id="progress">
    <div class="progress-bar"><div class="progress-fill" id="progressFill"></div></div>
    <div class="progress-text" id="progressText">Uploading...</div>
</div>

<div class="count" id="count"></div>
<div class="gallery" id="gallery"></div>

<div class="toast" id="toast"></div>
<div class="modal" id="modal" onclick="this.classList.remove('active')">
    <span class="modal-close">&times;</span>
    <img id="modalImg" src="">
</div>

<script>
const dropZone = document.getElementById('dropZone');
const fileInput = document.getElementById('fileInput');
const gallery = document.getElementById('gallery');
const progress = document.getElementById('progress');
const progressFill = document.getElementById('progressFill');
const progressText = document.getElementById('progressText');
const countEl = document.getElementById('count');

dropZone.addEventListener('click', () => fileInput.click());
dropZone.addEventListener('dragover', (e) => { e.preventDefault(); dropZone.classList.add('drag-over'); });
dropZone.addEventListener('dragleave', () => dropZone.classList.remove('drag-over'));
dropZone.addEventListener('drop', (e) => {
    e.preventDefault();
    dropZone.classList.remove('drag-over');
    handleFiles(e.dataTransfer.files);
});
fileInput.addEventListener('change', () => handleFiles(fileInput.files));

async function handleFiles(files) {
    if (!files.length) return;
    progress.style.display = 'block';
    let done = 0;
    for (const file of files) {
        progressText.textContent = `Uploading ${done+1}/${files.length}: ${file.name}`;
        progressFill.style.width = ((done / files.length) * 100) + '%';
        const formData = new FormData();
        formData.append('file', file);
        try {
            const resp = await fetch('/upload', { method: 'POST', body: formData });
            const result = await resp.json();
            if (result.ok) done++;
        } catch (err) {
            console.error(err);
        }
    }
    progressFill.style.width = '100%';
    progressText.textContent = `Done! ${done}/${files.length} uploaded`;
    showToast(`${done} file(s) uploaded successfully`);
    setTimeout(() => { progress.style.display = 'none'; }, 2000);
    loadGallery();
    fileInput.value = '';
}

function showToast(msg) {
    const t = document.getElementById('toast');
    t.textContent = msg;
    t.style.display = 'block';
    setTimeout(() => t.style.display = 'none', 3000);
}

function showModal(src) {
    document.getElementById('modalImg').src = src;
    document.getElementById('modal').classList.add('active');
}

async function deleteFile(name) {
    if (!confirm('Delete ' + name + '?')) return;
    await fetch('/delete?name=' + encodeURIComponent(name), { method: 'DELETE' });
    loadGallery();
}

async function loadGallery() {
    const resp = await fetch('/list');
    const files = await resp.json();
    countEl.textContent = files.length ? files.length + ' photos uploaded' : 'No photos yet';
    gallery.innerHTML = files.map(f => `
        <div class="gallery-item">
            <img src="/photos/${encodeURIComponent(f.name)}" onclick="showModal(this.src)" loading="lazy">
            <div class="info">
                <span class="delete-btn" onclick="deleteFile('${f.name}')">[delete]</span>
                <div class="name">${f.name}</div>
                <div class="meta">${f.size} &middot; ${f.time}</div>
            </div>
        </div>
    `).join('');
}

loadGallery();
</script>
</body>
</html>"""


class UploadHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        pass  # quiet

    def do_GET(self):
        if self.path == '/' or self.path == '/index.html':
            self.send_response(200)
            self.send_header('Content-Type', 'text/html; charset=utf-8')
            self.end_headers()
            self.wfile.write(HTML_PAGE.encode())

        elif self.path == '/list':
            files = []
            for f in sorted(UPLOAD_DIR.iterdir(), key=lambda x: x.stat().st_mtime, reverse=True):
                if f.is_file() and not f.name.startswith('.'):
                    st = f.stat()
                    size = f"{st.st_size / 1024:.0f}KB" if st.st_size < 1048576 else f"{st.st_size / 1048576:.1f}MB"
                    t = datetime.fromtimestamp(st.st_mtime).strftime('%m/%d %H:%M')
                    files.append({"name": f.name, "size": size, "time": t})
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps(files).encode())

        elif self.path.startswith('/photos/'):
            fname = urllib.parse.unquote(self.path[8:])
            fpath = UPLOAD_DIR / fname
            if fpath.exists() and fpath.is_file():
                ext = fpath.suffix.lower()
                ct = {'jpg': 'image/jpeg', 'jpeg': 'image/jpeg', 'png': 'image/png',
                      'gif': 'image/gif', 'webp': 'image/webp', 'heic': 'image/heic',
                      'pdf': 'application/pdf'}.get(ext.lstrip('.'), 'application/octet-stream')
                self.send_response(200)
                self.send_header('Content-Type', ct)
                self.send_header('Cache-Control', 'max-age=3600')
                self.end_headers()
                self.wfile.write(fpath.read_bytes())
            else:
                self.send_response(404)
                self.end_headers()
        else:
            self.send_response(404)
            self.end_headers()

    def do_POST(self):
        if self.path == '/upload':
            content_type = self.headers.get('Content-Type', '')
            if 'multipart/form-data' not in content_type:
                self.send_response(400)
                self.end_headers()
                self.wfile.write(b'{"ok":false,"error":"not multipart"}')
                return

            form = cgi.FieldStorage(fp=self.rfile, headers=self.headers,
                                     environ={'REQUEST_METHOD': 'POST',
                                              'CONTENT_TYPE': content_type})
            file_item = form['file']
            if file_item.filename:
                safe_name = os.path.basename(file_item.filename)
                # Avoid overwrite: add suffix if exists
                dest = UPLOAD_DIR / safe_name
                if dest.exists():
                    stem = dest.stem
                    suffix = dest.suffix
                    i = 1
                    while dest.exists():
                        dest = UPLOAD_DIR / f"{stem}_{i}{suffix}"
                        i += 1
                dest.write_bytes(file_item.file.read())
                self.send_response(200)
                self.send_header('Content-Type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({"ok": True, "name": dest.name}).encode())
            else:
                self.send_response(400)
                self.end_headers()
                self.wfile.write(b'{"ok":false}')
        else:
            self.send_response(404)
            self.end_headers()

    def do_DELETE(self):
        if self.path.startswith('/delete?'):
            qs = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
            name = qs.get('name', [''])[0]
            if name:
                fpath = UPLOAD_DIR / os.path.basename(name)
                if fpath.exists():
                    fpath.unlink()
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(b'{"ok":true}')
        else:
            self.send_response(404)
            self.end_headers()


if __name__ == '__main__':
    port = 3444
    print(f"Upload server running on http://localhost:{port}")
    print(f"Files saved to: {UPLOAD_DIR}")
    HTTPServer(('0.0.0.0', port), UploadHandler).serve_forever()
