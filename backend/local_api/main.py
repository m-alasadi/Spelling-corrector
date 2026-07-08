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
from enum import Enum
from typing import List, Optional

from fastapi import FastAPI, UploadFile, File, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, Field

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
# Pydantic Models — Two-Step Pipeline
# ──────────────────────────────────────────────────────────────

class ProcessingMode(str, Enum):
    preserve = "preserve"  # Keep dialect, fix grammar only
    msa = "msa"            # Convert to Modern Standard Arabic

class Stage2Request(BaseModel):
    """Request body for Stage 2: Grammar & Style."""
    text: str = Field(..., description="Clean text from Stage 1")
    add_punctuation: bool = Field(False, description="Add punctuation marks?")
    mode: ProcessingMode = Field(
        ProcessingMode.preserve,
        description="'preserve' = keep dialect, 'msa' = convert to formal Arabic"
    )

class SpellCheckRequest(BaseModel):
    """Request body for Stage 1: Spell Check."""
    text: str = Field(..., description="Raw text to spell-check")

class SegmentInput(BaseModel):
    id: int
    text: str

class Stage1BatchRequest(BaseModel):
    """Batch request for Stage 1."""
    segments: List[SegmentInput]


# ──────────────────────────────────────────────────────────────
# Dynamic Prompt Builder — Stage 2
# ──────────────────────────────────────────────────────────────

def build_grammar_prompt(add_punctuation: bool, mode: ProcessingMode) -> str:
    """
    Build System Prompt dynamically based on user options.
    
    Args:
        add_punctuation: Whether to add punctuation marks.
        mode: 'preserve' (keep dialect) or 'msa' (convert to formal).
    
    Returns:
        System prompt string for OpenAI.
    """
    base = "أنت خبير لغوي متخصص في النحو العربي والصياغة.\n\n"

    # ── Dialect handling ──
    if mode == ProcessingMode.preserve:
        dialect_rule = """⚠️ قاعدة صارمة للهجة العامية:
- حافظ على اللهجة العامية تماماً.
- لا تحول الكلمات الدارجة إلى فصحى.
- أمثلة: "عندنا" تبقى "عندنا"، "هسه" تبقى "هسه"، "شلون" تبقى "شلون".
- قم بتصحيح القواعد النحوية (الإعراب، الرفع، النصب) للكلمات الفصحى فقط.

"""
    else:  # msa
        dialect_rule = """⚠️ قاعدة تحويل الفصحى:
- أعد صياغة النص بأسلوب احترافي وبليغ.
- حوّل جميع الكلمات والأساليب العامية إلى لغة عربية فصحى رسمية.
- حافظ على المعنى الأصلي مع تحسين الأسلوب.
- مثال: "عندنا مشكلة" → "لدينا مشكلة"، "هسه" → "الآن".

"""

    # ── Punctuation handling ──
    if add_punctuation:
        punct_rule = """📝 قاعدة الترقيم:
- أضف علامات الترقيم المناسبة (فواصل، نقاط، علامات استفهام) لتنظيم النص.
- ضع الفواصل في مواضع التوقف المنطقية.
- ضع النقاط في نهاية الجمل.

"""
    else:
        punct_rule = """📝 تحذير صارم للترقيم:
- لا تقم بإضافة أو تعديل أي علامات ترقيم.
- احتفظ بجميع النقاط والفواصل والمسافات كما هي بالضبط.

"""

    # ── Common rules ──
    common = """قواعد عامة:
1. لا تُضيف كلمات جديدة ولا تحذف كلمات موجودة.
2. حافظ على بنية الجملة الأصلية.
3. إذا النص صحيح، أرجعه كما هو بدون أي تعديل.
4. أعد النص فقط بدون أي شرح أو تعليق.
"""

    return base + dialect_rule + punct_rule + common


# ──────────────────────────────────────────────────────────────
# Diffing Strategy — Smart N-to-M
# ──────────────────────────────────────────────────────────────

def compute_smart_diff(original: str, corrected: str) -> list:
    """
    Smart diff that handles N-to-M word changes (merge/split).
    Used for MSA mode where AI might merge or split words.
    """
    import difflib

    if not original or not original.strip():
        return [{'type': 'word', 'value': original or '', 'is_error': False, 'suggestion': None}]

    orig_tokens = tokenize_arabic(original)
    corr_tokens = tokenize_arabic(corrected)

    orig_words = [t['value'] for t in orig_tokens if t['type'] == 'word']
    corr_words = [t['value'] for t in corr_tokens if t['type'] == 'word']

    matcher = difflib.SequenceMatcher(None, orig_words, corr_words, autojunk=False)

    corrections = {}
    for op, i1, i2, j1, j2 in matcher.get_opcodes():
        if op == 'equal':
            for k in range(i1, i2):
                corrections[k] = {'is_error': False, 'suggestion': None}

        elif op == 'replace':
            orig_slice = orig_words[i1:i2]
            corr_slice = corr_words[j1:j2]
            orig_count = i2 - i1
            corr_count = j2 - j1

            if orig_count == corr_count:
                # 1-to-1 replacement
                for offset in range(orig_count):
                    corrections[i1 + offset] = {
                        'is_error': True,
                        'suggestion': corr_slice[offset]
                    }
            elif orig_count == 1 and corr_count > 1:
                # 1-to-N split: original word split into multiple
                corrections[i1] = {
                    'is_error': True,
                    'suggestion': ' '.join(corr_slice)
                }
            elif orig_count > 1 and corr_count == 1:
                # N-to-1 merge: multiple words merged into one
                corrections[i1] = {
                    'is_error': True,
                    'suggestion': corr_slice[0]
                }
                for k in range(i1 + 1, i2):
                    corrections[k] = {'is_error': True, 'suggestion': None, 'merged': True}
            else:
                # N-to-M: complex change
                corrections[i1] = {
                    'is_error': True,
                    'suggestion': ' '.join(corr_slice)
                }
                for k in range(i1 + 1, i2):
                    corrections[k] = {'is_error': True, 'suggestion': None, 'merged': True}

        elif op == 'delete':
            for k in range(i1, i2):
                corrections[k] = {'is_error': True, 'suggestion': ''}

    result = []
    word_idx = 0
    for token in orig_tokens:
        if token['type'] == 'word':
            corr = corrections.get(word_idx, {'is_error': False, 'suggestion': None})
            result.append({
                'type': 'word',
                'value': token['value'],
                'is_error': corr.get('is_error', False),
                'suggestion': corr.get('suggestion'),
                'merged': corr.get('merged', False),
            })
            word_idx += 1
        else:
            result.append({
                'type': token['type'],
                'value': token['value'],
                'is_error': False,
                'suggestion': None,
                'merged': False,
            })
    return result


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


# ──────────────────────────────────────────────────────────────
# Two-Step Pipeline: Stage 1 — Spell Check Only
# ──────────────────────────────────────────────────────────────

@app.post("/api/stage1/spell-check")
async def stage1_spell_check(req: SpellCheckRequest):
    """
    Stage 1: Spelling correction ONLY.
    - Uses local dictionary first.
    - Falls back to GPT-4o-mini with a STRICT spelling-only prompt.
    - Does NOT add punctuation.
    - Does NOT change dialect words.
    """
    from spell_checker import get_checker

    text = req.text.strip()
    if not text:
        raise HTTPException(status_code=400, detail="text is required")

    checker = get_checker()
    if not checker.client:
        raise HTTPException(status_code=503, detail="OpenAI API not configured")

    # 1. Dictionary check first
    dict_result = checker._correct_with_dict(text)
    if dict_result != text:
        # Dictionary fixed it — return immediately
        word_diffs = compute_word_diff(text, dict_result)
        return {
            "original": text,
            "corrected": dict_result,
            "word_diffs": word_diffs,
            "source": "dictionary",
        }

    # 2. AI spelling check (STRICT spelling-only prompt)
    spell_prompt = """أنت مدقق إملائي عربي محترف. مهمتك تصحيح الإملاء فقط.

ما تصححه (فقط):
- الهمزات: "اول" → "أول"، "ان" → "أن"
- الألفات: "الى" → "إلى"
- التاء المربوطة: "مئه" → "مئة"
- الحروف المقطوعة والمتصلة

ما لا تصححه مطلقاً:
- لا تُغيّر علامات الترقيم (نقاط، فواصل، علامات استفهام) — احتفظ بها كما هي بالضبط
- لا تصحح القواعد النحوية (الإعراب، الرفع، النصب، الجر، التنوين)
- لا تحوّل كلمات عامية إلى فصحى (احنا، هسه، شلون، عندنا — تبقى كما هي)
- لا تُضيف أو تحذف كلمات

إذا النص صحيح إملائياً، أرجعه كما هو بالضبط.
أعد النص فقط بدون أي شرح."""

    try:
        response = checker.client.chat.completions.create(
            model=checker.model,
            messages=[
                {"role": "system", "content": spell_prompt},
                {"role": "user", "content": f"صحح الإملاء فقط:\n\n{text}"}
            ],
            temperature=0,
            max_tokens=2000,
        )
        corrected = response.choices[0].message.content.strip()
        checker.stats['api_calls'] += 1

        if corrected != text:
            checker.cache.set(text, corrected, checker.model)

        word_diffs = compute_word_diff(text, corrected)
        return {
            "original": text,
            "corrected": corrected,
            "word_diffs": word_diffs,
            "source": "ai",
        }
    except Exception as e:
        logger.error(f"Stage 1 spell check failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/stage1/spell-check-batch")
async def stage1_spell_check_batch(req: Stage1BatchRequest):
    """
    Batch Stage 1: Spell check multiple segments.
    """
    from spell_checker import get_checker

    checker = get_checker()
    if not checker.client:
        raise HTTPException(status_code=503, detail="OpenAI API not configured")

    results = []
    for seg in req.segments:
        text = seg.text.strip()
        if not text:
            results.append({
                "id": seg.id,
                "original": text,
                "corrected": text,
                "word_diffs": [{'type': 'word', 'value': text, 'is_error': False, 'suggestion': None}],
                "source": "empty",
            })
            continue

        # Dictionary check
        dict_result = checker._correct_with_dict(text)
        if dict_result != text:
            results.append({
                "id": seg.id,
                "original": text,
                "corrected": dict_result,
                "word_diffs": compute_word_diff(text, dict_result),
                "source": "dictionary",
            })
            continue

        # AI check needed
        results.append({
            "id": seg.id,
            "original": text,
            "corrected": text,  # Will be filled by AI
            "word_diffs": [],
            "source": "pending",
        })

    # Batch AI check for pending segments
    pending = [(i, r) for i, r in enumerate(results) if r['source'] == 'pending']
    if pending and checker.client:
        texts = [r['original'] for _, r in pending]
        spell_prompt = """أنت مدقق إملائي عربي محترف. صحح الإملاء فقط.
ما تصححه: الهمزات (اول→أول، ان→أن)، الألفات (الى→إلى)، التاء المربوطة (مئه→مئة).
ما لا تصححه مطلقاً: لا تغيّر الترقيم ولا تصحح النحو ولا تحوّل عامية لفصحى (احنا، هسه، شلون تبقى).
إذا النص صحيح، أرجعه كما هو بالضبط.
أعد النصوص بالترتيب [1] [2]..."""

        numbered = "\n".join([f"[{i+1}] {t}" for i, t in enumerate(texts)])

        try:
            response = checker.client.chat.completions.create(
                model=checker.model,
                messages=[
                    {"role": "system", "content": spell_prompt},
                    {"role": "user", "content": f"صحح الإملاء فقط:\n\n{numbered}"}
                ],
                temperature=0,
                max_tokens=4000,
            )
            result_text = response.choices[0].message.content.strip()
            checker.stats['api_calls'] += 1

            # Parse numbered results
            pattern = r'\[(\d+)\]\s*(.*?)(?=\[\d+\]|$)'
            matches = re.findall(pattern, result_text, re.DOTALL)
            ai_map = {int(num): text.strip() for num, text in matches}

            for j, (idx, _) in enumerate(pending):
                ai_text = ai_map.get(j + 1, results[idx]['original'])
                if ai_text != results[idx]['original']:
                    results[idx]['corrected'] = ai_text
                    results[idx]['word_diffs'] = compute_word_diff(results[idx]['original'], ai_text)
                    results[idx]['source'] = 'ai'
                    checker.cache.set(results[idx]['original'], ai_text, checker.model)
                else:
                    results[idx]['word_diffs'] = [{'type': 'word', 'value': results[idx]['original'], 'is_error': False, 'suggestion': None}]
                    results[idx]['source'] = 'unchanged'
        except Exception as e:
            logger.error(f"Stage 1 batch AI failed: {e}")
            for idx, _ in pending:
                results[idx]['source'] = 'error'

    return {"results": results}


# ──────────────────────────────────────────────────────────────
# Two-Step Pipeline: Stage 2 — Grammar & Style
# ──────────────────────────────────────────────────────────────

@app.post("/api/stage2/grammar-style")
async def stage2_grammar_style(req: Stage2Request):
    """
    Stage 2: Grammar & Style processing.
    
    Dynamic prompt based on:
    - add_punctuation: whether to add punctuation
    - mode: 'preserve' (keep dialect) or 'msa' (convert to formal)
    """
    from spell_checker import get_checker

    text = req.text.strip()
    if not text:
        raise HTTPException(status_code=400, detail="text is required")

    checker = get_checker()
    if not checker.client:
        raise HTTPException(status_code=503, detail="OpenAI API not configured")

    # Build dynamic prompt
    system_prompt = build_grammar_prompt(req.add_punctuation, req.mode)

    try:
        response = checker.client.chat.completions.create(
            model=checker.model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": f"عالج النص التالي:\n\n{text}"}
            ],
            temperature=0.1,
            max_tokens=4000,
        )
        corrected = response.choices[0].message.content.strip()
        checker.stats['api_calls'] += 1

        # Use smart diff for N-to-M support
        word_diffs = compute_smart_diff(text, corrected)

        return {
            "original": text,
            "corrected": corrected,
            "word_diffs": word_diffs,
            "mode": req.mode.value,
            "punctuation_added": req.add_punctuation,
        }
    except Exception as e:
        logger.error(f"Stage 2 grammar check failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/stage2/grammar-style-batch")
async def stage2_grammar_style_batch(
    segments: List[SegmentInput],
    add_punctuation: bool = False,
    mode: ProcessingMode = ProcessingMode.preserve,
):
    """
    Batch Stage 2: Grammar & Style for multiple segments.
    """
    from spell_checker import get_checker

    checker = get_checker()
    if not checker.client:
        raise HTTPException(status_code=503, detail="OpenAI API not configured")

    system_prompt = build_grammar_prompt(add_punctuation, mode)

    # Build numbered prompt
    numbered = "\n".join(
        [f"[{s.id}] {s.text}" for s in segments if s.text.strip()]
    )
    if not numbered:
        return {"results": []}

    try:
        response = checker.client.chat.completions.create(
            model=checker.model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": f"عالج النصوص التالية:\n\n{numbered}"}
            ],
            temperature=0.1,
            max_tokens=4000,
        )
        result_text = response.choices[0].message.content.strip()
        checker.stats['api_calls'] += 1

        # Parse numbered results
        pattern = r'\[(\d+)\]\s*(.*?)(?=\[\d+\]|$)'
        matches = re.findall(pattern, result_text, re.DOTALL)
        results_map = {int(num): text.strip() for num, text in matches}

        results = []
        for seg in segments:
            original = seg.text
            corrected = results_map.get(seg.id, original)
            results.append({
                'id': seg.id,
                'original': original,
                'corrected': corrected,
                'word_diffs': compute_smart_diff(original, corrected),
            })

        return {"results": results}
    except Exception as e:
        logger.error(f"Stage 2 batch grammar check failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/grammar-check")
async def grammar_check(request: Request):
    """
    On-demand grammar check for selected text.
    Uses OpenAI to correct grammatical errors (إعراب، رفع، نصب، جر)
    while preserving colloquial/dialect words.
    """
    body = await request.json()
    text = body.get('text', '').strip()
    
    if not text:
        raise HTTPException(status_code=400, detail="text is required")
    
    # Import OpenAI client from spell_checker
    from spell_checker import get_checker
    checker = get_checker()
    
    if not checker.client:
        raise HTTPException(status_code=503, detail="OpenAI API not configured")
    
    system_prompt = """أنت خبير في النحو العربي. مهمتك هي تصحيح الأخطاء النحوية فقط.

⚠️ أهم قاعدة (افتحها أولاً):
أي كلمة عامية أو لهجية (عراقية، شامية، خليجية، مصرية...) يُمنع منعاً باتاً تعديلها أو حذفها أو استبدالها. إذا استبدلت كلمة عامية بأي كلمة أخرى، أنت خاطئ.

أمثلة على كلمات عامية يُمنع تعديلها:
- عندنا = صحيحة (لا تحوّلها إلى "لدينا" أو "أن")
- هسه = صحيحة (لا تحوّلها إلى "الآن")
- شنو = صحيحة (لا تحوّلها إلى "ماذا")
- وين = صحيحة (لا تحوّلها إلى "أين")
- هاي = صحيحة (لا تحوّلها إلى "هذه")
- شلون = صحيحة (لا تحوّلها إلى "كيف")
- اريد = صحيحة (لا تحوّلها إلى "أريد")
- لوّن = صحيحة (لا تحوّلها إلى "يميل")

ما يُصحَّح (الإعراب فقط):
- فاعل + مفعول به: "جاء الرجلُ البيتَ" (لم يجئ الرجل)
- رفع ونصب الضمائر: "رأيتُهُ" (لا "رأيته")
- الإضافة: "كتابُ الطالبِ" (لا "كتاب الطالب")
- همزة الوصل والقطع: "ابن" vs "ابْن" (لا تغيّر)

قواعد صارمة:
1. صحح الإعراب فقط (رفع، نصب، جر، ضمائر)
2. لا تحوّل أي كلمة عامية إلى فصحى
3. لا تُضِف أو تحذف كلمات
4. لا تُغيّر علامات الترقيم
5. إذا النص صحيح نحوياً، أرجعه كما هو 100%
6. أعد النص فقط بدون شرح
"""
    
    try:
        response = checker.client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": f"صحح الأخطاء النحوية في النص التالي (لا تلمس الكلمات العامية):\n\n{text}"}
            ],
            temperature=0,
            max_tokens=2000,
        )
        
        corrected = response.choices[0].message.content.strip()
        
        return {
            "original_text": text,
            "corrected_text": corrected,
        }
    except Exception as e:
        logger.error(f"Grammar check failed: {e}")
        raise HTTPException(status_code=500, detail=f"Grammar check failed: {str(e)}")


@app.post("/api/grammar-check-batch")
async def grammar_check_batch(request: Request):
    """
    Batch grammar check for all segments.
    Body: { "segments": [{ "id": 1, "text": "..." }, ...] }
    Returns: { "results": [{ "id": 1, "original": "...", "corrected": "..." }, ...] }
    """
    from spell_checker import get_checker
    body = await request.json()
    segments = body.get('segments', [])
    
    if not segments:
        raise HTTPException(status_code=400, detail="segments is required")
    
    checker = get_checker()
    if not checker.client:
        raise HTTPException(status_code=503, detail="OpenAI API not configured")
    
    system_prompt = """أنت خبير في النحو العربي. مهمتك هي تصحيح الأخطاء النحوية فقط.

⚠️ أهم قاعدة (افتحها أولاً):
أي كلمة عامية أو لهجية يُمنع منعاً باتاً تعديلها أو استبدالها.

أمثلة على كلمات عامية يُمنع تعديلها:
- عندنا، هسه، شنو، وين، هاي، شلون، اريد، لوّن

ما يُصحَّح فقط (الإعراب):
- فاعل + مفعول به: "جاء الرجلُ البيتَ"
- رفع ونصب الضمائر
- الإضافة: "كتابُ الطالبِ"

قواعد صارمة:
1. صحح الإعراب فقط
2. لا تحوّل كلمة عامية إلى فصحى
3. لا تُضِف أو تحذف كلمات
4. لا تُغيّر علامات الترقيم
5. إذا النص صحيح نحوياً، أرجعه كما هو
6. أعد النص فقط بدون شرح
"""
    
    # Build numbered prompt
    numbered = "\n".join([f"[{s['id']}] {s['text']}" for s in segments if s.get('text', '').strip()])
    
    if not numbered:
        return {"results": []}
    
    try:
        response = checker.client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": f"صحح الأخطاء النحوية في كل نص:\n\n{numbered}"}
            ],
            temperature=0,
            max_tokens=4000,
        )
        
        result_text = response.choices[0].message.content.strip()
        
        # Parse numbered results
        import re as _re
        results = []
        pattern = r'\[(\d+)\]\s*(.*?)(?=\[\d+\]|$)'
        matches = _re.findall(pattern, result_text, _re.DOTALL)
        
        results_map = {}
        for num_str, text in matches:
            results_map[int(num_str)] = text.strip()
        
        for seg in segments:
            seg_id = seg['id']
            original = seg.get('text', '')
            corrected = results_map.get(seg_id, original)
            results.append({
                'id': seg_id,
                'original': original,
                'corrected': corrected,
            })
        
        return {"results": results}
    except Exception as e:
        logger.error(f"Grammar batch check failed: {e}")
        raise HTTPException(status_code=500, detail=f"Grammar batch check failed: {str(e)}")


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
