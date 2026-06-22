#!/usr/bin/env python3
"""
Spell Corrector Web Interface
=============================
A Flask-based web interface for uploading ASR files, viewing errors, and correcting them.

Usage:
    python web_app.py

Then open: http://localhost:5000
"""

import json
import os
import re
import sys
import uuid
import logging
import difflib
from pathlib import Path
from datetime import datetime
from flask import Flask, render_template, request, jsonify, send_file

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Add current directory to path
sys.path.insert(0, str(Path(__file__).parent))

from corrector import SpellCorrector
from corrector_fast import FastSpellCorrector, get_fast_corrector
from file_converter import FileConverter, get_supported_formats

app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max file size
app.config['UPLOAD_FOLDER'] = str(Path(__file__).parent / 'uploads')
app.config['OUTPUT_FOLDER'] = str(Path(__file__).parent / 'exports')

# Ensure folders exist
Path(app.config['UPLOAD_FOLDER']).mkdir(exist_ok=True)
Path(app.config['OUTPUT_FOLDER']).mkdir(exist_ok=True)

# Store correction results temporarily
correction_results = {}


# ──────────────────────────────────────────────────────────────
# Word-level diff utilities
# ──────────────────────────────────────────────────────────────

def tokenize_arabic_text(text):
    """
    Tokenize Arabic text into words and separators while preserving order.
    Returns list of {type: 'word'|'space'|'punct', value: str}
    """
    tokens = []
    # Match Arabic words, whitespace sequences, or punctuation/other chars
    for match in re.finditer(r'[\u0600-\u06FF\u0750-\u077F\u08A0-\u08FF\uFB50-\uFDFF\uFE70-\uFEFF]+|\s+|[^\s\u0600-\u06FF\u0750-\u077F\u08A0-\u08FF\uFB50-\uFDFF\uFE70-\uFEFF]+', text):
        val = match.group()
        if val.isspace():
            tokens.append({'type': 'space', 'value': val})
        elif re.match(r'[\u0600-\u06FF\u0750-\u077F\u08A0-\u08FF\uFB50-\uFDFF\uFE70-\uFEFF]+', val):
            tokens.append({'type': 'word', 'value': val})
        else:
            tokens.append({'type': 'punct', 'value': val})
    return tokens


def compute_word_diff(original, corrected):
    """
    Compare original and corrected text word-by-word.
    Returns a list of token objects with correction info.
    Each token: {type, value, is_error, suggestion}
    """
    if not original or not original.strip():
        return [{'type': 'word', 'value': original or '', 'is_error': False, 'suggestion': None}]

    orig_tokens = [t for t in tokenize_arabic_text(original) if t['type'] != 'space']
    corr_tokens = [t for t in tokenize_arabic_text(corrected) if t['type'] != 'space']

    # Use SequenceMatcher on word values
    orig_words = [t['value'] for t in orig_tokens]
    corr_words = [t['value'] for t in corr_tokens]

    matcher = difflib.SequenceMatcher(None, orig_words, corr_words, autojunk=False)

    # Build a map: orig_word_index -> correction info
    corrections = {}
    for op, i1, i2, j1, j2 in matcher.get_opcodes():
        if op == 'equal':
            for k in range(i1, i2):
                corrections[k] = {'is_error': False, 'suggestion': None}
        elif op == 'replace':
            corr_text = ' '.join(corr_words[j1:j2])
            for k in range(i1, i2):
                corrections[k] = {'is_error': True, 'suggestion': corr_text}
        elif op == 'delete':
            for k in range(i1, i2):
                corrections[k] = {'is_error': True, 'suggestion': ''}

    # Reconstruct full token list with correction info
    result = []
    word_idx = 0
    for token in tokenize_arabic_text(original):
        if token['type'] == 'word':
            corr = corrections.get(word_idx, {'is_error': False, 'suggestion': None})
            result.append({
                'type': 'word',
                'value': token['value'],
                'is_error': corr['is_error'],
                'suggestion': corr['suggestion']
            })
            word_idx += 1
        else:
            result.append({
                'type': token['type'],
                'value': token['value'],
                'is_error': False,
                'suggestion': None
            })

    return result


def compute_all_diffs(segments):
    """
    Compute word-level diffs for all segments.
    Mutates segments in place, adding 'word_diffs' to each.
    Returns total error count.
    """
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


@app.route('/')
def index():
    """Main page - Upload file"""
    return render_template('index.html')


@app.route('/upload', methods=['POST'])
def upload_file():
    """Handle file upload and initial parsing"""
    if 'file' not in request.files:
        return jsonify({'error': 'No file uploaded'}), 400
    
    file = request.files['file']
    if file.filename == '':
        return jsonify({'error': 'No file selected'}), 400
    
    # Check supported formats
    supported = get_supported_formats()
    file_ext = Path(file.filename).suffix.lower()
    
    if file_ext not in supported:
        return jsonify({
            'error': f'Unsupported format: {file_ext}',
            'supported': supported
        }), 400
    
    try:
        # Generate unique job ID
        job_id = str(uuid.uuid4())[:8]
        
        # Save uploaded file
        upload_path = Path(app.config['UPLOAD_FOLDER']) / f"{job_id}_{file.filename}"
        file.save(str(upload_path))
        
        # Convert to JSON segments using FileConverter
        data = FileConverter.convert(str(upload_path))
        
        # Validate we have segments
        if not data.get('segments'):
            return jsonify({'error': 'No text content found in file'}), 400
        
        # Store in memory for processing
        correction_results[job_id] = {
            'data': data,
            'filename': file.filename,
            'upload_path': str(upload_path),
            'status': 'uploaded',
            'created_at': datetime.now().isoformat()
        }
        
        # Count segments
        total_segments = len(data.get('segments', []))
        segments_with_text = sum(1 for s in data['segments'] if s.get('text_original', '').strip())
        
        return jsonify({
            'success': True,
            'job_id': job_id,
            'filename': file.filename,
            'total_segments': total_segments,
            'segments_with_text': segments_with_text,
            'preview': data['segments'][:5] if data['segments'] else []
        })
        
    except json.JSONDecodeError as e:
        return jsonify({'error': f'Invalid JSON: {str(e)}'}), 400
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/preview/<job_id>')
def preview(job_id):
    """Preview page showing segments before correction"""
    if job_id not in correction_results:
        return render_template('error.html', message='Job not found'), 404
    
    result = correction_results[job_id]
    return render_template('preview.html', 
                          job_id=job_id,
                          data=result['data'],
                          filename=result['filename'])


@app.route('/correct/<job_id>', methods=['POST'])
def correct_file(job_id):
    """Process the file and apply corrections"""
    if job_id not in correction_results:
        return jsonify({'error': 'Job not found'}), 404
    
    try:
        result = correction_results[job_id]
        data = result['data']
        segments = data.get('segments', [])
        total = len(segments)
        
        logger.info(f"Starting correction for {total} segments")
        
        # Use fast corrector for large files, regular for small
        if total > 20:
            corrector = get_fast_corrector(model="gpt-3.5-turbo")
            data = corrector.correct_large_file(data)
            stats = corrector.get_stats()
            corrected_count = stats['corrected_segments']
        else:
            # Small file - use regular corrector
            corrector = SpellCorrector()
            texts = [s.get('text_original', '') for s in segments]
            corrected = corrector.correct_batch_optimized(texts, batch_size=5)
            corrected_count = 0
            for i, (seg, corr) in enumerate(zip(segments, corrected)):
                seg['text_corrected'] = corr
                if corr and corr != seg.get('text_original', ''):
                    corrected_count += 1
        
        # Save corrected file
        output_filename = f"corrected_{result['filename']}"
        output_path = Path(app.config['OUTPUT_FOLDER']) / f"{job_id}_{output_filename}"
        
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        
        # Update status
        result['status'] = 'corrected'
        result['output_path'] = str(output_path)
        result['corrected_count'] = corrected_count
        
        # Compute word-level diffs for the editor
        total_errors = compute_all_diffs(segments)
        result['total_errors'] = total_errors
        
        return jsonify({
            'success': True,
            'corrected_count': corrected_count,
            'total_segments': len(segments),
            'output_filename': output_filename,
            'total_errors': total_errors,
            'editor_url': f'/editor/{job_id}'
        })
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/results/<job_id>')
def results(job_id):
    """Results page showing before/after comparison"""
    if job_id not in correction_results:
        return render_template('error.html', message='Job not found'), 404
    
    result = correction_results[job_id]
    
    if result['status'] != 'corrected':
        return render_template('error.html', message='File not yet corrected'), 400
    
    return render_template('results.html',
                          job_id=job_id,
                          data=result['data'],
                          filename=result['filename'],
                          corrected_count=result.get('corrected_count', 0))


@app.route('/download/<job_id>')
def download(job_id):
    """Download corrected file"""
    if job_id not in correction_results:
        return jsonify({'error': 'Job not found'}), 404
    
    result = correction_results[job_id]
    
    if result['status'] != 'corrected':
        return jsonify({'error': 'File not yet corrected'}), 400
    
    output_path = result['output_path']
    if not os.path.exists(output_path):
        return jsonify({'error': 'Output file not found'}), 404
    
    return send_file(
        output_path,
        as_attachment=True,
        download_name=f"corrected_{result['filename']}"
    )


@app.route('/api/correct-text', methods=['POST'])
def correct_single_text():
    """API endpoint for correcting single text"""
    try:
        data = request.get_json()
        text = data.get('text', '')
        language = data.get('language', 'ar-SA')
        
        if not text:
            return jsonify({'error': 'No text provided'}), 400
        
        corrector = SpellCorrector()
        corrected = corrector.correct_text(text, language)
        
        return jsonify({
            'success': True,
            'original': text,
            'corrected': corrected
        })
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/progress/<job_id>')
def progress_stream(job_id):
    """Server-Sent Events endpoint for real-time progress"""
    from flask import Response
    
    def generate():
        import time
        
        if job_id not in correction_results:
            yield f"data: {json.dumps({'error': 'Job not found'})}\n\n"
            return
        
        result = correction_results[job_id]
        data = result['data']
        segments = data.get('segments', [])
        total = len(segments)
        
        yield f"data: {json.dumps({'current': 0, 'total': total, 'message': 'بدء المعالجة...'})}\n\n"
        
        # Use fast corrector
        corrector = get_fast_corrector(model="gpt-3.5-turbo")
        
        def progress_callback(current, total_count, message):
            # This will be called by the corrector
            pass
        
        # Process and stream progress
        start_time = time.time()
        
        # Process in batches and yield progress
        texts_to_correct = []
        indices = []
        
        for i, seg in enumerate(segments):
            text = seg.get('text_original', '')
            if text and text.strip():
                texts_to_correct.append(text)
                indices.append(i)
            else:
                seg['text_corrected'] = text
        
        total_to_correct = len(texts_to_correct)
        batch_size = 15
        
        for batch_start in range(0, total_to_correct, batch_size):
            batch = texts_to_correct[batch_start:batch_start + batch_size]
            batch_indices = indices[batch_start:batch_start + batch_size]
            
            try:
                results = corrector._call_api(batch, data.get('language', 'ar-SA'))
                
                for idx, corrected in zip(batch_indices, results):
                    segments[idx]['text_corrected'] = corrected
                    cache_key = corrector._get_cache_key(segments[idx]['text_original'])
                    corrector.cache[cache_key] = corrected
                    corrector.stats['corrected_segments'] += 1
                
                current = batch_start + len(batch)
                elapsed = time.time() - start_time
                speed = current / elapsed if elapsed > 0 else 0
                remaining = (total_to_correct - current) / speed if speed > 0 else 0
                
                yield f"data: {json.dumps({'current': current, 'total': total_to_correct, 'message': f'تم {current}/{total_to_correct}', 'elapsed': round(elapsed, 1), 'remaining': round(remaining, 1)})}\n\n"
                
            except Exception as e:
                logger.error(f"Batch error: {e}")
                for idx, text in zip(batch_indices, batch):
                    segments[idx]['text_corrected'] = text
                yield f"data: {json.dumps({'current': batch_start + len(batch), 'total': total_to_correct, 'message': f'خطأ في دفعة - تم التخطي'})}\n\n"
        
        # Save results
        output_filename = f"corrected_{result['filename']}"
        output_path = Path(app.config['OUTPUT_FOLDER']) / f"{job_id}_{output_filename}"
        
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        
        result['status'] = 'corrected'
        result['output_path'] = str(output_path)
        result['corrected_count'] = corrector.stats['corrected_segments']
        
        # Compute word-level diffs for the editor
        total_errors = compute_all_diffs(segments)
        result['total_errors'] = total_errors
        
        elapsed = time.time() - start_time
        yield f"data: {json.dumps({'done': True, 'corrected': corrector.stats['corrected_segments'], 'duration': round(elapsed, 1), 'output_filename': output_filename, 'total_errors': total_errors, 'editor_url': f'/editor/{job_id}'})}\n\n"
    
    return Response(generate(), mimetype='text/event-stream')


# ──────────────────────────────────────────────────────────────
# Editor routes
# ──────────────────────────────────────────────────────────────

@app.route('/editor/<job_id>')
def editor(job_id):
    """Interactive editor page with inline spell checking"""
    if job_id not in correction_results:
        return render_template('error.html', message='Job not found'), 404
    
    result = correction_results[job_id]
    
    if result['status'] != 'corrected':
        return render_template('error.html', message='File not yet corrected'), 400
    
    data = result['data']
    segments = data.get('segments', [])
    
    # Compute word-level diffs if not already done
    if not any('word_diffs' in seg for seg in segments):
        compute_all_diffs(segments)
    
    total_errors = sum(seg.get('error_count', 0) for seg in segments)
    
    return render_template('editor.html',
                          job_id=job_id,
                          data=data,
                          filename=result['filename'],
                          corrected_count=result.get('corrected_count', 0),
                          total_errors=total_errors)


@app.route('/api/apply-correction/<job_id>', methods=['POST'])
def apply_correction(job_id):
    """Apply a single word correction (accept or ignore)"""
    if job_id not in correction_results:
        return jsonify({'error': 'Job not found'}), 404
    
    try:
        payload = request.get_json()
        seg_index = payload.get('segment_index')
        word_index = payload.get('word_index')
        action = payload.get('action')  # 'accept' or 'ignore'
        
        result = correction_results[job_id]
        segments = result['data'].get('segments', [])
        
        if seg_index >= len(segments):
            return jsonify({'error': 'Invalid segment index'}), 400
        
        segment = segments[seg_index]
        word_diffs = segment.get('word_diffs', [])
        
        if word_index >= len(word_diffs):
            return jsonify({'error': 'Invalid word index'}), 400
        
        word = word_diffs[word_index]
        
        if action == 'accept':
            # Replace the word in text_corrected
            word['accepted'] = True
            word['ignored'] = False
        elif action == 'ignore':
            word['accepted'] = False
            word['ignored'] = True
        else:
            return jsonify({'error': 'Invalid action'}), 400
        
        # Recount errors
        remaining = sum(1 for w in word_diffs if w.get('is_error') and not w.get('accepted') and not w.get('ignored'))
        segment['error_count'] = remaining
        
        total_errors = sum(s.get('error_count', 0) for s in segments)
        
        return jsonify({
            'success': True,
            'remaining_errors': remaining,
            'total_errors': total_errors
        })
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/accept-all/<job_id>', methods=['POST'])
def accept_all_corrections(job_id):
    """Accept all remaining corrections"""
    if job_id not in correction_results:
        return jsonify({'error': 'Job not found'}), 404
    
    try:
        result = correction_results[job_id]
        segments = result['data'].get('segments', [])
        
        for seg in segments:
            for word in seg.get('word_diffs', []):
                if word.get('is_error'):
                    word['accepted'] = True
                    word['ignored'] = False
            seg['error_count'] = 0
        
        # Update text_corrected to reflect accepted changes
        for seg in segments:
            diffs = seg.get('word_diffs', [])
            if diffs:
                new_text = ''
                for w in diffs:
                    if w.get('is_error') and w.get('accepted'):
                        new_text += w.get('suggestion', w['value'])
                    else:
                        new_text += w['value']
                seg['text_corrected'] = new_text
        
        return jsonify({'success': True, 'total_errors': 0})
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/ignore-all/<job_id>', methods=['POST'])
def ignore_all_corrections(job_id):
    """Ignore all remaining corrections"""
    if job_id not in correction_results:
        return jsonify({'error': 'Job not found'}), 404
    
    try:
        result = correction_results[job_id]
        segments = result['data'].get('segments', [])
        
        for seg in segments:
            for word in seg.get('word_diffs', []):
                if word.get('is_error'):
                    word['accepted'] = False
                    word['ignored'] = True
            seg['error_count'] = 0
        
        return jsonify({'success': True, 'total_errors': 0})
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/download-edited/<job_id>')
def download_edited(job_id):
    """Download the final edited/corrected text"""
    if job_id not in correction_results:
        return jsonify({'error': 'Job not found'}), 404
    
    result = correction_results[job_id]
    
    if result['status'] != 'corrected':
        return jsonify({'error': 'File not yet corrected'}), 400
    
    data = result['data']
    segments = data.get('segments', [])
    
    # Build final text from word_diffs
    final_segments = []
    for seg in segments:
        diffs = seg.get('word_diffs', [])
        if diffs:
            text = ''
            for w in diffs:
                if w.get('is_error') and w.get('accepted') and not w.get('ignored'):
                    text += w.get('suggestion', w['value'])
                else:
                    text += w['value']
            final_segments.append(text)
        else:
            final_segments.append(seg.get('text_corrected', seg.get('text_original', '')))
    
    # Build output based on original format
    output_data = {
        'job_id': data.get('job_id', job_id),
        'source_file': data.get('source_file', ''),
        'language': data.get('language', 'ar-SA'),
        'engine': data.get('engine', ''),
        'segments': []
    }
    
    for i, seg in enumerate(segments):
        seg_data = {
            'id': seg.get('id', i + 1),
            'text_original': seg.get('text_original', ''),
            'text_corrected': final_segments[i] if i < len(final_segments) else seg.get('text_corrected', '')
        }
        if seg.get('speaker'):
            seg_data['speaker'] = seg['speaker']
        if seg.get('start'):
            seg_data['start'] = seg['start']
        if seg.get('end'):
            seg_data['end'] = seg['end']
        output_data['segments'].append(seg_data)
    
    output_filename = f"final_{result['filename']}"
    output_path = Path(app.config['OUTPUT_FOLDER']) / f"{job_id}_{output_filename}"
    
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(output_data, f, ensure_ascii=False, indent=2)
    
    return send_file(
        output_path,
        as_attachment=True,
        download_name=output_filename
    )


@app.route('/health')
def health():
    """Health check endpoint"""
    return jsonify({'status': 'ok', 'timestamp': datetime.now().isoformat()})


if __name__ == '__main__':
    print("=" * 50)
    print("🌐 Spell Corrector Web Interface")
    print("=" * 50)
    print()
    print("Opening browser at: http://localhost:5000")
    print()
    print("Press Ctrl+C to stop")
    print("=" * 50)
    
    app.run(debug=False, port=5000, host='0.0.0.0')
