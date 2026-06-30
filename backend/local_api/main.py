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
    """Parse uploaded file into segments. Auto-detects JSON content."""
    ext = Path(filename).suffix.lower()
    text = content.decode('utf-8')
    
    # Try JSON first (auto-detect even if extension is .txt)
    try:
        data = json.loads(text)
        if isinstance(data, dict):
            if 'segments' in data:
                return data
            elif 'text' in data:
                return _text_to_segments(data['text'], filename)
            # JSON object without segments/text — treat each value as segment
            elif any(isinstance(v, str) for v in data.values()):
                # Might be flat JSON like {"1": "text", "2": "text"}
                segments = []
                for k, v in data.items():
                    if isinstance(v, str) and v.strip():
                        segments.append({
                            'id': len(segments) + 1,
                            'text_original': v,
                            'text_corrected': None,
                            'speaker': None,
                        })
                if segments:
                    return {
                        'job_id': str(uuid.uuid4())[:8],
                        'source_file': filename,
                        'language': 'ar',
                        'segments': segments,
                    }
    except (json.JSONDecodeError, ValueError):
        pass
    
    # Not JSON — treat as plain text
    if ext in ('.txt', '.text'):
        return _text_to_segments(text, filename)
    
    elif ext == '.srt':
        return _parse_srt(text, filename)
    
    elif ext == '.vtt':
        return _parse_vtt(text, filename)
    
    # Fallback: try as text
    return _text_to_segments(text, filename)


def _text_to_segments(text: str, filename: str) -> dict:
    """
    Convert plain text to segments.
    Groups short consecutive lines into paragraphs.
    """
    lines = re.split(r'\n', text)
    segments = []
    current_paragraph = []
    
    for line in lines:
        stripped = line.strip()
        
        if not stripped:
            # Empty line = paragraph break
            if current_paragraph:
                para_text = ' '.join(current_paragraph)
                segments.append({
                    'id': len(segments) + 1,
                    'text_original': para_text,
                    'text_corrected': None,
                    'speaker': None,
                })
                current_paragraph = []
        else:
            current_paragraph.append(stripped)
    
    # Don't forget last paragraph
    if current_paragraph:
        para_text = ' '.join(current_paragraph)
        segments.append({
            'id': len(segments) + 1,
            'text_original': para_text,
            'text_corrected': None,
            'speaker': None,
        })
    
    # Fallback: if no paragraphs found, split by any newline
    if not segments:
        for i, line in enumerate(lines):
            stripped = line.strip()
            if stripped:
                segments.append({
                    'id': len(segments) + 1,
                    'text_original': stripped,
                    'text_corrected': None,
                    'speaker': None,
                })
    
    return {
        'job_id': str(uuid.uuid4())[:8],
        'source_file': filename,
        'language': 'ar',
        'segments': segments,
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
        
        # Return lightweight response (segments will come via SSE)
        return {
            'success': True,
            'job_id': job_id,
            'filename': file.filename,
            'total_segments': total_segments,
            'segments_with_text': segments_with_text,
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


# ──────────────────────────────────────────────────────────────
# Error Database: Track corrections
# ──────────────────────────────────────────────────────────────

@app.post("/api/corrections/save")
async def save_correction(request: Request):
    """
    Save a correction (AI or user manual).
    Body: {"original": "...", "corrected": "...", "context": "...", "source": "ai|user"}
    """
    from error_db import get_error_db
    from dictionary import get_dictionary
    
    body = await request.json()
    original = body.get('original', '').strip()
    corrected = body.get('corrected', '').strip()
    context = body.get('context', '')
    source = body.get('source', 'user')
    
    if not original or not corrected:
        raise HTTPException(status_code=400, detail="original and corrected are required")
    if original == corrected:
        raise HTTPException(status_code=400, detail="original and corrected must be different")
    
    db = get_error_db()
    db.save_correction(original, corrected, context, source)
    
    # Also add to dictionary for immediate effect
    d = get_dictionary()
    d.add_word(original, corrected)
    
    return {
        'success': True,
        'original': original,
        'corrected': corrected,
        'source': source,
        'message': f'تم حفظ التصحيح: {original} → {corrected}',
        'stats': db.get_stats(),
    }


@app.get("/api/corrections/stats")
async def get_correction_stats():
    """Get error database statistics."""
    from error_db import get_error_db
    db = get_error_db()
    return db.get_stats()


@app.get("/api/corrections/common")
async def get_common_errors(min_frequency: int = 2, limit: int = 50):
    """Get most common errors."""
    from error_db import get_error_db
    db = get_error_db()
    return {'errors': db.get_common_errors(min_frequency, limit)}


@app.get("/api/corrections/word/{word}")
async def get_word_corrections(word: str):
    """Get all corrections for a specific word."""
    from error_db import get_error_db
    db = get_error_db()
    return {'word': word, 'corrections': db.get_corrections_for_word(word)}


# ──────────────────────────────────────────────────────────────
# SSE: Real-time correction streaming
# ──────────────────────────────────────────────────────────────

@app.get("/correct-stream/{job_id}")
async def correct_stream(job_id: str):
    """
    SSE endpoint: streams corrections using PARALLEL processing.
    
    Uses ThreadPoolExecutor for parallel API calls.
    Results are streamed as they complete.
    """
    from fastapi.responses import StreamingResponse
    import threading
    from concurrent.futures import ThreadPoolExecutor, as_completed
    
    if job_id not in jobs:
        async def error_gen():
            yield f"data: {json.dumps({'type': 'error', 'message': 'Job not found'})}\n\n"
        return StreamingResponse(error_gen(), media_type="text/event-stream")
    
    job = jobs[job_id]
    data = job['data']
    segments = data.get('segments', [])
    language = data.get('language', 'ar')
    
    async def event_generator():
        checker = get_checker()
        total = len(segments)
        
        # ── Step 1: Send all segments immediately (raw text) ──
        init_segments = []
        for seg in segments:
            init_segments.append({
                'id': seg.get('id'),
                'text_original': seg.get('text_original', ''),
                'text_corrected': seg.get('text_corrected'),
                'speaker': seg.get('speaker'),
                'word_diffs': seg.get('word_diffs'),
            })
        
        yield f"data: {json.dumps({'type': 'init', 'segments': init_segments, 'filename': job['filename']})}\n\n"
        
        # ── Step 2: Pre-filter + Dict + Cache (instant, parallel) ──
        segments_needing_ai = []  # (index, text)
        
        for i, seg in enumerate(segments):
            text = seg.get('text_original', '')
            
            if not text or not text.strip():
                # Empty segment — mark as done
                yield f"data: {json.dumps({'type': 'segment', 'index': i, 'text_corrected': text, 'word_diffs': [{'type': 'word', 'value': text or '', 'is_error': False, 'suggestion': None}], 'error_count': 0})}\n\n"
                continue
            
            # Pre-filter check
            from spell_checker import should_skip_ai
            if should_skip_ai(text):
                yield f"data: {json.dumps({'type': 'segment', 'index': i, 'text_corrected': text, 'word_diffs': [{'type': 'word', 'value': text, 'is_error': False, 'suggestion': None}], 'error_count': 0})}\n\n"
                continue
            
            # Cache check
            cached = checker.cache.get(text)
            if cached is not None:
                word_diffs = compute_word_diff(text, cached)
                error_count = sum(1 for w in word_diffs if w.get('is_error'))
                seg['text_corrected'] = cached
                seg['word_diffs'] = word_diffs
                seg['error_count'] = error_count
                yield f"data: {json.dumps({'type': 'segment', 'index': i, 'text_corrected': cached, 'word_diffs': word_diffs, 'error_count': error_count})}\n\n"
                continue
            
            # Dictionary check
            dict_result = checker._correct_with_dict(text)
            if dict_result != text:
                word_diffs = compute_word_diff(text, dict_result)
                error_count = sum(1 for w in word_diffs if w.get('is_error'))
                seg['text_corrected'] = dict_result
                seg['word_diffs'] = word_diffs
                seg['error_count'] = error_count
                checker.cache.set(text, dict_result, checker.model)
                yield f"data: {json.dumps({'type': 'segment', 'index': i, 'text_corrected': dict_result, 'word_diffs': word_diffs, 'error_count': error_count})}\n\n"
                continue
            
            # Needs AI — collect for parallel processing
            segments_needing_ai.append((i, text))
        
        # ── Step 3: AI processing (PARALLEL with Semaphore) ──
        if segments_needing_ai and checker.client:
            batch_size = 30
            semaphore = threading.Semaphore(5)
            
            # Split into batches
            batches = []
            for batch_start in range(0, len(segments_needing_ai), batch_size):
                batch = segments_needing_ai[batch_start:batch_start + batch_size]
                batches.append(batch)
            
            def process_batch(batch):
                texts = [t for _, t in batch]
                indices = [i for i, _ in batch]
                
                with semaphore:
                    # Call AI for the batch
                    ai_results = checker._call_ai_batch(texts, language)
                
                return list(zip(indices, ai_results))
            
            # Process batches in parallel
            with ThreadPoolExecutor(max_workers=5) as executor:
                futures = [executor.submit(process_batch, b) for b in batches]
                
                for future in as_completed(futures):
                    try:
                        batch_results = future.result()
                        for idx, ai_text in batch_results:
                            original_text = segments[idx].get('text_original', '')
                            
                            if ai_text and ai_text != original_text:
                                word_diffs = compute_word_diff(original_text, ai_text)
                                error_count = sum(1 for w in word_diffs if w.get('is_error'))
                                segments[idx]['text_corrected'] = ai_text
                                segments[idx]['word_diffs'] = word_diffs
                                segments[idx]['error_count'] = error_count
                                checker.cache.set(original_text, ai_text, checker.model)
                            else:
                                # No change
                                word_diffs = [{'type': 'word', 'value': original_text, 'is_error': False, 'suggestion': None}]
                                segments[idx]['text_corrected'] = original_text
                                segments[idx]['word_diffs'] = word_diffs
                                segments[idx]['error_count'] = 0
                            
                            # Stream this segment result
                            yield f"data: {json.dumps({'type': 'segment', 'index': idx, 'text_corrected': segments[idx]['text_corrected'], 'word_diffs': word_diffs, 'error_count': error_count})}\n\n"
                    
                    except Exception as e:
                        logger.error(f"Batch error: {e}")
        
        # ── Step 4: Final summary ──
        corrected_count = sum(1 for s in segments if s.get('text_corrected') != s.get('text_original'))
        total_errors = sum(s.get('error_count', 0) for s in segments)
        
        # Save output
        output_path = EXPORT_DIR / f"{job_id}_corrected.json"
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        
        job['status'] = 'corrected'
        job['output_path'] = str(output_path)
        job['corrected_count'] = corrected_count
        
        stats = checker.get_stats()
        yield f"data: {json.dumps({'type': 'done', 'corrected_count': corrected_count, 'total_errors': total_errors, 'stats': stats})}\n\n"
    
    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            'Cache-Control': 'no-cache',
            'Connection': 'keep-alive',
            'X-Accel-Buffering': 'no',
        }
    )


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
