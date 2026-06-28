#!/usr/bin/env python3
"""
FastAPI Spell Corrector Server
==============================
Local API backend for the interactive spell editor.

Endpoints:
  POST /upload          - Upload and parse file
  POST /correct/{id}    - Run spell correction
  GET  /editor/{id}     - Interactive editor page
  POST /api/apply       - Apply single word correction
  POST /api/accept-all  - Accept all corrections
  POST /api/ignore-all  - Ignore all corrections
  GET  /api/download    - Download corrected file
  GET  /api/stats/{id}  - Get correction stats
"""

import os
import re
import json
import uuid
import logging
from pathlib import Path
from datetime import datetime

from fastapi import FastAPI, UploadFile, File, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

import sys
sys.path.insert(0, str(Path(__file__).parent))

from spell_checker import SpellChecker, get_checker, compute_word_diff, tokenize_arabic
from dictionary import get_dictionary

# ── Logging ──
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ── App Setup ──
app = FastAPI(title="Arabic Spell Corrector API", version="2.0")

# Paths
BASE_DIR = Path(__file__).parent
UPLOAD_DIR = BASE_DIR / "uploads"
EXPORT_DIR = BASE_DIR / "exports"
TEMPLATE_DIR = BASE_DIR / "templates"

UPLOAD_DIR.mkdir(exist_ok=True)
EXPORT_DIR.mkdir(exist_ok=True)

templates = Jinja2Templates(directory=str(TEMPLATE_DIR))

# In-memory job storage
jobs = {}


# ──────────────────────────────────────────────────────────────
# Helper Functions
# ──────────────────────────────────────────────────────────────

def parse_uploaded_file(content: bytes, filename: str) -> dict:
    """Parse uploaded file into segments."""
    ext = Path(filename).suffix.lower()
    
    if ext == '.json':
        data = json.loads(content.decode('utf-8'))
        if 'segments' not in data:
            # Try to parse as simple text JSON
            if 'text' in data:
                data = _text_to_segments(data['text'], filename)
            else:
                raise ValueError("JSON file must contain 'segments' or 'text' key")
        return data
    
    elif ext == '.txt':
        text = content.decode('utf-8')
        return _text_to_segments(text, filename)
    
    elif ext == '.srt':
        text = content.decode('utf-8')
        return _parse_srt(text, filename)
    
    elif ext == '.vtt':
        text = content.decode('utf-8')
        return _parse_vtt(text, filename)
    
    else:
        raise ValueError(f"Unsupported format: {ext}")


def _text_to_segments(text: str, filename: str) -> dict:
    """Convert plain text to segments."""
    paragraphs = re.split(r'\n\s*\n|\n', text)
    segments = []
    for i, para in enumerate(paragraphs):
        para = para.strip()
        if para:
            segments.append({
                'id': i + 1,
                'text_original': para,
                'text_corrected': None,
                'speaker': None,
            })
    return {
        'job_id': str(uuid.uuid4())[:8],
        'source_file': filename,
        'language': 'ar',
        'segments': segments
    }


def _parse_srt(text: str, filename: str) -> dict:
    """Parse SRT subtitle format."""
    segments = []
    blocks = re.split(r'\n\n+', text.strip())
    
    for block in blocks:
        lines = block.strip().split('\n')
        if len(lines) >= 3:
            time_match = re.search(r'(\d{2}:\d{2}:\d{2})', lines[1])
            if time_match:
                text_line = ' '.join(lines[2:])
                segments.append({
                    'id': len(segments) + 1,
                    'text_original': text_line,
                    'text_corrected': None,
                    'speaker': None,
                })
    
    return {
        'job_id': str(uuid.uuid4())[:8],
        'source_file': filename,
        'language': 'ar',
        'segments': segments
    }


def _parse_vtt(text: str, filename: str) -> dict:
    """Parse WebVTT format."""
    content = re.sub(r'^WEBVTT.*?\n\n', '', text, flags=re.DOTALL)
    return _parse_srt(content, filename)


def compute_all_diffs(segments: list) -> int:
    """Compute word-level diffs for all segments. Returns total error count."""
    total_errors = 0
    for seg in segments:
        original = seg.get('text_original', '')
        corrected = seg.get('text_corrected', original)
        if original and corrected:
            seg['word_diffs'] = compute_word_diff(original, corrected)
            seg['error_count'] = sum(1 for t in seg['word_diffs'] if t.get('is_error'))
            total_errors += seg['error_count']
        else:
            seg['word_diffs'] = [{'type': 'word', 'value': original or '', 'is_error': False, 'suggestion': None}]
            seg['error_count'] = 0
    return total_errors


# ──────────────────────────────────────────────────────────────
# Routes: Pages
# ──────────────────────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    """Main upload page."""
    return templates.TemplateResponse("index.html", {"request": request})


@app.get("/editor/{job_id}", response_class=HTMLResponse)
async def editor_page(request: Request, job_id: str):
    """Interactive spell-checking editor."""
    if job_id not in jobs:
        raise HTTPException(status_code=404, detail="Job not found")
    
    job = jobs[job_id]
    if job['status'] != 'corrected':
        raise HTTPException(status_code=400, detail="File not yet corrected")
    
    data = job['data']
    segments = data.get('segments', [])
    
    # Compute word-level diffs
    total_errors = compute_all_diffs(segments)
    
    return templates.TemplateResponse("editor.html", {
        "request": request,
        "job_id": job_id,
        "data": data,
        "filename": job['filename'],
        "corrected_count": job.get('corrected_count', 0),
        "total_errors": total_errors,
    })


# ──────────────────────────────────────────────────────────────
# Routes: API
# ──────────────────────────────────────────────────────────────

@app.post("/upload")
async def upload_file(file: UploadFile = File(...)):
    """Upload and parse a file into segments."""
    if not file.filename:
        raise HTTPException(status_code=400, detail="No file selected")
    
    supported = ['.json', '.txt', '.srt', '.vtt']
    ext = Path(file.filename).suffix.lower()
    if ext not in supported:
        raise HTTPException(status_code=400, detail=f"Unsupported format: {ext}")
    
    try:
        content = await file.read()
        data = parse_uploaded_file(content, file.filename)
        
        if not data.get('segments'):
            raise HTTPException(status_code=400, detail="No text content found")
        
        job_id = str(uuid.uuid4())[:8]
        jobs[job_id] = {
            'data': data,
            'filename': file.filename,
            'status': 'uploaded',
            'created_at': datetime.now().isoformat(),
        }
        
        total_segments = len(data['segments'])
        segments_with_text = sum(1 for s in data['segments'] if s.get('text_original', '').strip())
        
        return {
            'success': True,
            'job_id': job_id,
            'filename': file.filename,
            'total_segments': total_segments,
            'segments_with_text': segments_with_text,
            'preview': data['segments'][:5],
            'data': data,
        }
    except json.JSONDecodeError as e:
        raise HTTPException(status_code=400, detail=f"Invalid JSON: {e}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/correct/{job_id}")
async def correct_file(job_id: str, model: str = "gpt-4o-mini"):
    """Run spell correction on uploaded file."""
    if job_id not in jobs:
        raise HTTPException(status_code=404, detail="Job not found")
    
    job = jobs[job_id]
    data = job['data']
    segments = data.get('segments', [])
    
    logger.info(f"Starting correction for {len(segments)} segments")
    
    checker = get_checker(model)
    
    # Get texts to correct
    texts = [s.get('text_original', '') for s in segments]
    
    # Correct batch
    corrected = checker.correct_batch(texts, data.get('language', 'ar'))
    
    corrected_count = 0
    for seg, corr in zip(segments, corrected):
        seg['text_corrected'] = corr
        if corr and corr != seg.get('text_original', ''):
            corrected_count += 1
    
    # Save output
    output_path = EXPORT_DIR / f"{job_id}_corrected.json"
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    
    job['status'] = 'corrected'
    job['output_path'] = str(output_path)
    job['corrected_count'] = corrected_count
    
    stats = checker.get_stats()
    
    return {
        'success': True,
        'job_id': job_id,
        'corrected_count': corrected_count,
        'total_segments': len(segments),
        'editor_url': f'/editor/{job_id}',
        'stats': stats,
    }


@app.post("/api/apply")
async def apply_correction(request: Request):
    """Apply a single word correction (accept or ignore)."""
    body = await request.json()
    job_id = body.get('job_id')
    seg_index = body.get('segment_index')
    word_index = body.get('word_index')
    action = body.get('action')
    
    if job_id not in jobs:
        raise HTTPException(status_code=404, detail="Job not found")
    
    segments = jobs[job_id]['data'].get('segments', [])
    if seg_index >= len(segments):
        raise HTTPException(status_code=400, detail="Invalid segment index")
    
    segment = segments[seg_index]
    word_diffs = segment.get('word_diffs', [])
    if word_index >= len(word_diffs):
        raise HTTPException(status_code=400, detail="Invalid word index")
    
    word = word_diffs[word_index]
    
    if action == 'accept':
        word['accepted'] = True
        word['ignored'] = False
    elif action == 'ignore':
        word['accepted'] = False
        word['ignored'] = True
    
    # Recount
    remaining = sum(1 for w in word_diffs if w.get('is_error') and not w.get('accepted') and not w.get('ignored'))
    segment['error_count'] = remaining
    total_errors = sum(s.get('error_count', 0) for s in segments)
    
    return {'success': True, 'remaining_errors': remaining, 'total_errors': total_errors}


@app.post("/api/accept-all")
async def accept_all(request: Request):
    """Accept all corrections for a job."""
    body = await request.json()
    job_id = body.get('job_id')
    
    if job_id not in jobs:
        raise HTTPException(status_code=404, detail="Job not found")
    
    segments = jobs[job_id]['data'].get('segments', [])
    for seg in segments:
        for word in seg.get('word_diffs', []):
            if word.get('is_error'):
                word['accepted'] = True
                word['ignored'] = False
        seg['error_count'] = 0
    
    return {'success': True, 'total_errors': 0}


@app.post("/api/ignore-all")
async def ignore_all(request: Request):
    """Ignore all corrections for a job."""
    body = await request.json()
    job_id = body.get('job_id')
    
    if job_id not in jobs:
        raise HTTPException(status_code=404, detail="Job not found")
    
    segments = jobs[job_id]['data'].get('segments', [])
    for seg in segments:
        for word in seg.get('word_diffs', []):
            if word.get('is_error'):
                word['accepted'] = False
                word['ignored'] = True
        seg['error_count'] = 0
    
    return {'success': True, 'total_errors': 0}


@app.get("/api/download/{job_id}")
async def download_file(job_id: str):
    """Download corrected file."""
    if job_id not in jobs:
        raise HTTPException(status_code=404, detail="Job not found")
    
    job = jobs[job_id]
    if job['status'] != 'corrected':
        raise HTTPException(status_code=400, detail="File not yet corrected")
    
    output_path = job.get('output_path')
    if not output_path or not os.path.exists(output_path):
        raise HTTPException(status_code=404, detail="Output file not found")
    
    return FileResponse(
        output_path,
        filename=f"corrected_{job['filename']}",
        media_type="application/json"
    )


@app.get("/api/stats/{job_id}")
async def get_stats(job_id: str):
    """Get correction statistics for a job."""
    if job_id not in jobs:
        raise HTTPException(status_code=404, detail="Job not found")
    
    job = jobs[job_id]
    return {
        'job_id': job_id,
        'status': job['status'],
        'corrected_count': job.get('corrected_count', 0),
        'filename': job['filename'],
    }


@app.get("/api/job/{job_id}")
async def get_job_data(job_id: str):
    """Get full job data with word_diffs for the React frontend."""
    if job_id not in jobs:
        raise HTTPException(status_code=404, detail="Job not found")
    
    job = jobs[job_id]
    data = job['data']
    segments = data.get('segments', [])
    
    # Compute word-level diffs if not already done
    if not any('word_diffs' in seg for seg in segments):
        compute_all_diffs(segments)
    
    total_errors = sum(seg.get('error_count', 0) for seg in segments)
    
    return {
        'job_id': job_id,
        'filename': job['filename'],
        'status': job['status'],
        'corrected_count': job.get('corrected_count', 0),
        'total_errors': total_errors,
        'data': data,
    }


@app.get("/api/dictionary")
async def get_dict_info():
    """Get dictionary statistics."""
    d = get_dictionary()
    return d.get_stats()


@app.get("/api/dictionary/words")
async def get_dict_words():
    """Get all words in the dictionary."""
    d = get_dictionary()
    return {'words': d.get_all_words(), 'count': len(d.get_all_words())}


@app.post("/api/dictionary/add")
async def add_to_dictionary(request: Request):
    """
    Add a word to the dictionary dynamically.
    Body: {"word": "الكلمة", "correction": "التصحيح"} or {"word": "الكلمة"}
    If correction is provided: adds as error => correction rule
    If correction is None: adds as known correct word
    """
    body = await request.json()
    word = body.get('word', '').strip()
    correction = body.get('correction')
    
    if not word:
        raise HTTPException(status_code=400, detail="Word is required")
    
    if correction:
        correction = correction.strip()
    
    d = get_dictionary()
    success = d.add_word(word, correction)
    
    if not success:
        raise HTTPException(status_code=500, detail="Failed to add word")
    
    return {
        'success': True,
        'word': word,
        'correction': correction,
        'message': f'تمت إضافة "{word}" إلى القاموس',
        'stats': d.get_stats(),
    }


@app.get("/api/cache/stats")
async def get_cache_stats():
    """Get cache statistics."""
    checker = get_checker()
    return checker.cache.stats()


@app.get("/health")
async def health():
    """Health check."""
    return {'status': 'ok', 'timestamp': datetime.now().isoformat()}


# ──────────────────────────────────────────────────────────────
# Run
# ──────────────────────────────────────────────────────────────

if __name__ == '__main__':
    import uvicorn
    print("=" * 50)
    print("🚀 FastAPI Arabic Spell Corrector")
    print("=" * 50)
    print("Server: http://localhost:8000")
    print("Docs:   http://localhost:8000/docs")
    print("=" * 50)
    uvicorn.run(app, host="0.0.0.0", port=8000)
