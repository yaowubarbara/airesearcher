"""Simple file upload server for AI Researcher.

Run with: python3 upload_server.py
Then expose with: cloudflared tunnel --url http://localhost:8899
"""

import os
import shutil
from datetime import datetime
from pathlib import Path

from fastapi import FastAPI, File, UploadFile, Request
from fastapi.responses import HTMLResponse, JSONResponse
import uvicorn

UPLOAD_DIR = Path("data/style_samples")
PAPERS_DIR = Path("data/papers")
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
PAPERS_DIR.mkdir(parents=True, exist_ok=True)

app = FastAPI()

HTML_PAGE = """\
<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>AI Researcher - PDF Upload</title>
<style>
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
         background: #0f172a; color: #e2e8f0; min-height: 100vh; padding: 2rem; }
  .container { max-width: 800px; margin: 0 auto; }
  h1 { font-size: 1.5rem; margin-bottom: 0.5rem; color: #38bdf8; }
  .subtitle { color: #94a3b8; margin-bottom: 2rem; font-size: 0.9rem; }

  .tab-bar { display: flex; gap: 4px; margin-bottom: 1.5rem; }
  .tab { padding: 0.6rem 1.2rem; border-radius: 8px 8px 0 0; cursor: pointer;
         background: #1e293b; color: #94a3b8; border: 1px solid #334155;
         border-bottom: none; font-size: 0.9rem; transition: all 0.2s; }
  .tab.active { background: #1e293b; color: #38bdf8; border-color: #38bdf8;
                border-bottom: 2px solid #1e293b; position: relative; top: 1px; }
  .tab:hover { color: #e2e8f0; }

  .drop-zone { border: 2px dashed #334155; border-radius: 12px; padding: 3rem;
               text-align: center; transition: all 0.3s; cursor: pointer;
               background: #1e293b; }
  .drop-zone.dragover { border-color: #38bdf8; background: #1e3a5f; }
  .drop-zone p { color: #94a3b8; margin-bottom: 0.5rem; }
  .drop-zone .icon { font-size: 3rem; margin-bottom: 1rem; }
  .drop-zone .hint { font-size: 0.8rem; color: #64748b; }

  .file-input { display: none; }

  .progress-bar { height: 4px; background: #334155; border-radius: 2px;
                  margin-top: 1rem; overflow: hidden; display: none; }
  .progress-fill { height: 100%; background: #38bdf8; width: 0%; transition: width 0.3s; }

  .file-list { margin-top: 2rem; }
  .file-list h2 { font-size: 1.1rem; color: #cbd5e1; margin-bottom: 0.75rem; }
  .file-item { display: flex; justify-content: space-between; align-items: center;
               padding: 0.6rem 1rem; background: #1e293b; border-radius: 8px;
               margin-bottom: 0.5rem; border: 1px solid #334155; }
  .file-item .name { color: #e2e8f0; font-size: 0.9rem; word-break: break-all; }
  .file-item .meta { color: #64748b; font-size: 0.8rem; white-space: nowrap; margin-left: 1rem; }
  .file-item .delete-btn { background: none; border: none; color: #ef4444; cursor: pointer;
                           font-size: 1.1rem; padding: 0.2rem 0.5rem; margin-left: 0.5rem;
                           border-radius: 4px; }
  .file-item .delete-btn:hover { background: #7f1d1d; }

  .status { margin-top: 1rem; padding: 0.75rem 1rem; border-radius: 8px;
            font-size: 0.9rem; display: none; }
  .status.success { display: block; background: #064e3b; color: #6ee7b7; border: 1px solid #065f46; }
  .status.error { display: block; background: #7f1d1d; color: #fca5a5; border: 1px solid #991b1b; }

  .empty { text-align: center; color: #475569; padding: 2rem; }
</style>
</head>
<body>
<div class="container">
  <h1>AI Researcher - PDF Upload</h1>
  <p class="subtitle">Upload PDFs for style learning or reference papers</p>

  <div class="tab-bar">
    <div class="tab active" data-target="style_samples" onclick="switchTab(this)">
      Style Samples (learn writing style)
    </div>
    <div class="tab" data-target="papers" onclick="switchTab(this)">
      Reference Papers (for citation)
    </div>
  </div>

  <div class="drop-zone" id="dropZone">
    <div class="icon">&#128196;</div>
    <p>Drag & drop PDF files here</p>
    <p class="hint">or click to select files</p>
    <input type="file" class="file-input" id="fileInput" multiple accept=".pdf">
  </div>

  <div class="progress-bar" id="progressBar">
    <div class="progress-fill" id="progressFill"></div>
  </div>

  <div class="status" id="status"></div>

  <div class="file-list" id="fileList"></div>
</div>

<script>
let currentTarget = 'style_samples';

function switchTab(el) {
  document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
  el.classList.add('active');
  currentTarget = el.dataset.target;
  loadFiles();
}

const dropZone = document.getElementById('dropZone');
const fileInput = document.getElementById('fileInput');
const progressBar = document.getElementById('progressBar');
const progressFill = document.getElementById('progressFill');
const statusEl = document.getElementById('status');

dropZone.addEventListener('click', () => fileInput.click());
dropZone.addEventListener('dragover', e => { e.preventDefault(); dropZone.classList.add('dragover'); });
dropZone.addEventListener('dragleave', () => dropZone.classList.remove('dragover'));
dropZone.addEventListener('drop', e => {
  e.preventDefault();
  dropZone.classList.remove('dragover');
  handleFiles(e.dataTransfer.files);
});
fileInput.addEventListener('change', () => handleFiles(fileInput.files));

async function handleFiles(files) {
  const pdfs = Array.from(files).filter(f => f.name.toLowerCase().endsWith('.pdf'));
  if (!pdfs.length) { showStatus('Please select PDF files only.', 'error'); return; }

  progressBar.style.display = 'block';
  progressFill.style.width = '0%';
  statusEl.style.display = 'none';

  let uploaded = 0;
  for (const file of pdfs) {
    const formData = new FormData();
    formData.append('file', file);
    formData.append('target', currentTarget);
    try {
      const resp = await fetch('/upload', { method: 'POST', body: formData });
      const data = await resp.json();
      if (!resp.ok) throw new Error(data.detail || 'Upload failed');
      uploaded++;
    } catch (err) {
      showStatus(`Failed: ${file.name} - ${err.message}`, 'error');
    }
    progressFill.style.width = ((uploaded / pdfs.length) * 100) + '%';
  }

  progressBar.style.display = 'none';
  if (uploaded > 0) {
    showStatus(`Successfully uploaded ${uploaded} file(s)`, 'success');
    loadFiles();
  }
  fileInput.value = '';
}

function showStatus(msg, type) {
  statusEl.textContent = msg;
  statusEl.className = 'status ' + type;
}

async function loadFiles() {
  const resp = await fetch('/files?target=' + currentTarget);
  const files = await resp.json();
  const list = document.getElementById('fileList');

  if (!files.length) {
    list.innerHTML = '<div class="empty">No files uploaded yet</div>';
    return;
  }

  const label = currentTarget === 'style_samples' ? 'Style Sample PDFs' : 'Reference Papers';
  list.innerHTML = '<h2>' + label + ' (' + files.length + ')</h2>' +
    files.map(f => `
      <div class="file-item">
        <span class="name">${f.name}</span>
        <span>
          <span class="meta">${f.size}</span>
          <button class="delete-btn" onclick="deleteFile('${f.name}')" title="Delete">&times;</button>
        </span>
      </div>
    `).join('');
}

async function deleteFile(name) {
  if (!confirm('Delete ' + name + '?')) return;
  await fetch('/files/' + encodeURIComponent(name) + '?target=' + currentTarget, { method: 'DELETE' });
  loadFiles();
}

loadFiles();
</script>
</body>
</html>
"""


@app.get("/", response_class=HTMLResponse)
async def index():
    return HTML_PAGE


@app.post("/upload")
async def upload(file: UploadFile = File(...), target: str = "style_samples"):
    if not file.filename or not file.filename.lower().endswith(".pdf"):
        return JSONResponse({"detail": "Only PDF files are accepted"}, status_code=400)

    dest_dir = UPLOAD_DIR if target == "style_samples" else PAPERS_DIR
    safe_name = file.filename.replace("/", "_").replace("\\", "_")
    dest = dest_dir / safe_name

    with open(dest, "wb") as f:
        shutil.copyfileobj(file.file, f)

    size = dest.stat().st_size
    return {"name": safe_name, "size": size, "path": str(dest)}


@app.get("/files")
async def list_files(target: str = "style_samples"):
    dest_dir = UPLOAD_DIR if target == "style_samples" else PAPERS_DIR
    files = []
    for p in sorted(dest_dir.glob("*.pdf"), key=lambda x: x.stat().st_mtime, reverse=True):
        size = p.stat().st_size
        if size > 1_000_000:
            size_str = f"{size / 1_000_000:.1f} MB"
        else:
            size_str = f"{size / 1_000:.0f} KB"
        files.append({"name": p.name, "size": size_str})
    return files


@app.delete("/files/{name}")
async def delete_file(name: str, target: str = "style_samples"):
    dest_dir = UPLOAD_DIR if target == "style_samples" else PAPERS_DIR
    path = dest_dir / name
    if path.exists():
        path.unlink()
        return {"deleted": name}
    return JSONResponse({"detail": "File not found"}, status_code=404)


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8899)
