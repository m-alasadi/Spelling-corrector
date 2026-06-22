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
import sys
import uuid
import logging
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
        
        return jsonify({
            'success': True,
            'corrected_count': corrected_count,
            'total_segments': len(segments),
            'output_filename': output_filename
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
        
        elapsed = time.time() - start_time
        yield f"data: {json.dumps({'done': True, 'corrected': corrector.stats['corrected_segments'], 'duration': round(elapsed, 1), 'output_filename': output_filename})}\n\n"
    
    return Response(generate(), mimetype='text/event-stream')


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
    
    app.run(debug=True, port=5000, host='0.0.0.0')
