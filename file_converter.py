#!/usr/bin/env python3
"""
File Format Converter
=====================
Converts various text formats to JSON segments for spell correction.

Supported formats:
    - .json (ASR output)
    - .txt (plain text)
    - .srt (subtitle files)
    - .pdf (PDF documents)
    - .docx (Word documents)
"""

import json
import os
import re
from pathlib import Path
from typing import List, Dict, Any, Optional
from datetime import datetime


class FileConverter:
    """Convert various file formats to JSON segments."""
    
    @staticmethod
    def detect_format(file_path: str) -> str:
        """Detect file format from extension."""
        ext = Path(file_path).suffix.lower()
        format_map = {
            '.json': 'json',
            '.txt': 'txt',
            '.srt': 'srt',
            '.pdf': 'pdf',
            '.docx': 'docx',
            '.doc': 'docx',
            '.vtt': 'vtt',
            '.sub': 'sub'
        }
        return format_map.get(ext, 'unknown')
    
    @staticmethod
    def convert(file_path: str) -> Dict[str, Any]:
        """
        Convert file to standard JSON format.
        
        Returns:
            Dictionary with job metadata and segments array
        """
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"File not found: {file_path}")
        
        converter = FileConverter()
        format_type = converter.detect_format(file_path)
        
        converters = {
            'json': converter._convert_json,
            'txt': converter._convert_txt,
            'srt': converter._convert_srt,
            'pdf': converter._convert_pdf,
            'docx': converter._convert_docx,
            'vtt': converter._convert_vtt,
        }
        
        converter_func = converters.get(format_type)
        if not converter_func:
            raise ValueError(f"Unsupported format: {format_type}")
        
        return converter_func(file_path)
    
    def _convert_json(self, file_path: str) -> Dict[str, Any]:
        """Convert JSON ASR output (existing format)."""
        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        # Ensure proper structure
        if 'segments' not in data:
            data = {
                'job_id': str(os.urandom(8).hex()),
                'source_file': Path(file_path).name,
                'language': 'ar-SA',
                'engine': 'json-import',
                'segments': []
            }
            
            # Convert simple text to segments
            if isinstance(data.get('text'), str):
                data['segments'] = self._text_to_segments(data['text'])
        
        return data
    
    def _convert_txt(self, file_path: str) -> Dict[str, Any]:
        """Convert plain text file to segments."""
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        return self._create_output(
            source_file=file_path,
            segments=self._text_to_segments(content)
        )
    
    def _convert_srt(self, file_path: str) -> Dict[str, Any]:
        """Convert SRT subtitle file to segments."""
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # Parse SRT format
        segments = []
        blocks = re.split(r'\n\n+', content.strip())
        
        for i, block in enumerate(blocks):
            lines = block.strip().split('\n')
            if len(lines) >= 3:
                # Parse timestamp
                time_match = re.match(
                    r'(\d{2}):(\d{2}):(\d{2})[,.](\d{3})\s*-->\s*(\d{2}):(\d{2}):(\d{2})[,.](\d{3})',
                    lines[1]
                )
                
                if time_match:
                    start_ms = self._time_to_ms(
                        int(lines[1].split('-->')[0].strip().replace(',', '.'))
                    )
                    end_ms = self._time_to_ms(
                        int(lines[1].split('-->')[1].strip().replace(',', '.'))
                    )
                    
                    text = ' '.join(lines[2:])
                    
                    segments.append({
                        'id': i + 1,
                        'start_ms': start_ms,
                        'end_ms': end_ms,
                        'speaker': None,
                        'text_original': text,
                        'text_corrected': None
                    })
        
        return self._create_output(
            source_file=file_path,
            segments=segments
        )
    
    def _convert_vtt(self, file_path: str) -> Dict[str, Any]:
        """Convert WebVTT subtitle file to segments."""
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # Remove VTT header
        content = re.sub(r'^WEBVTT.*?\n\n', '', content, flags=re.DOTALL)
        
        # Parse as SRT-like format
        segments = []
        blocks = re.split(r'\n\n+', content.strip())
        
        for i, block in enumerate(blocks):
            lines = block.strip().split('\n')
            
            for j, line in enumerate(lines):
                time_match = re.match(
                    r'(\d{2}:\d{2}:\d{2}\.\d{3})\s*-->\s*(\d{2}:\d{2}:\d{2}\.\d{3})',
                    line
                )
                
                if time_match:
                    text = ' '.join(lines[j+1:])
                    if text.strip():
                        segments.append({
                            'id': len(segments) + 1,
                            'start_ms': self._vtt_time_to_ms(time_match.group(1)),
                            'end_ms': self._vtt_time_to_ms(time_match.group(2)),
                            'speaker': None,
                            'text_original': text.strip(),
                            'text_corrected': None
                        })
                    break
        
        return self._create_output(
            source_file=file_path,
            segments=segments
        )
    
    def _convert_pdf(self, file_path: str) -> Dict[str, Any]:
        """Convert PDF file to segments."""
        try:
            import pdfplumber
            
            segments = []
            with pdfplumber.open(file_path) as pdf:
                for page_num, page in enumerate(pdf.pages):
                    text = page.extract_text()
                    if text and text.strip():
                        # Split by paragraphs
                        paragraphs = [p.strip() for p in text.split('\n\n') if p.strip()]
                        
                        for para in paragraphs:
                            segments.append({
                                'id': len(segments) + 1,
                                'start_ms': 0,
                                'end_ms': 0,
                                'speaker': None,
                                'text_original': para,
                                'text_corrected': None
                            })
            
            return self._create_output(
                source_file=file_path,
                segments=segments
            )
            
        except ImportError:
            raise ImportError(
                "PDF support requires pdfplumber. Install it with:\n"
                "pip install pdfplumber"
            )
    
    def _convert_docx(self, file_path: str) -> Dict[str, Any]:
        """Convert Word document to segments."""
        try:
            from docx import Document
            
            doc = Document(file_path)
            segments = []
            
            for para in doc.paragraphs:
                text = para.text.strip()
                if text:
                    segments.append({
                        'id': len(segments) + 1,
                        'start_ms': 0,
                        'end_ms': 0,
                        'speaker': None,
                        'text_original': text,
                        'text_corrected': None
                    })
            
            return self._create_output(
                source_file=file_path,
                segments=segments
            )
            
        except ImportError:
            raise ImportError(
                "Word support requires python-docx. Install it with:\n"
                "pip install python-docx"
            )
    
    def _text_to_segments(self, text: str) -> List[Dict[str, Any]]:
        """Convert plain text to segments by splitting into paragraphs."""
        # Split by double newline or single newline
        paragraphs = re.split(r'\n\s*\n|\n', text)
        
        segments = []
        for i, para in enumerate(paragraphs):
            para = para.strip()
            if para:  # Skip empty paragraphs
                segments.append({
                    'id': i + 1,
                    'start_ms': 0,
                    'end_ms': 0,
                    'speaker': None,
                    'text_original': para,
                    'text_corrected': None
                })
        
        return segments
    
    def _create_output(self, source_file: str, segments: List[Dict]) -> Dict[str, Any]:
        """Create standard output format."""
        return {
            'job_id': str(os.urandom(8).hex()),
            'source_file': Path(source_file).name,
            'language': 'ar-SA',
            'engine': 'file-import',
            'duration_ms': 0,
            'created_at': datetime.now().isoformat(),
            'segments': segments
        }
    
    @staticmethod
    def _time_to_ms(time_val: int) -> int:
        """Convert time value to milliseconds."""
        # Assuming HH:MM:SS.mmm format
        return time_val
    
    @staticmethod
    def _vtt_time_to_ms(time_str: str) -> int:
        """Convert VTT timestamp to milliseconds."""
        match = re.match(r'(\d{2}):(\d{2}):(\d{2})\.(\d{3})', time_str)
        if match:
            hours = int(match.group(1))
            minutes = int(match.group(2))
            seconds = int(match.group(3))
            ms = int(match.group(4))
            return (hours * 3600 + minutes * 60 + seconds) * 1000 + ms
        return 0


def get_supported_formats() -> List[str]:
    """Return list of supported file extensions."""
    return ['.json', '.txt', '.srt', '.vtt', '.pdf', '.docx', '.doc']


if __name__ == "__main__":
    # Test the converter
    import sys
    
    if len(sys.argv) < 2:
        print("Usage: python file_converter.py <file_path>")
        print(f"Supported formats: {', '.join(get_supported_formats())}")
        sys.exit(1)
    
    file_path = sys.argv[1]
    
    try:
        result = FileConverter.convert(file_path)
        print(f"✅ Converted successfully!")
        print(f"   Segments: {len(result['segments'])}")
        print(f"   Language: {result['language']}")
        
        # Show first 3 segments
        for seg in result['segments'][:3]:
            print(f"\n   [{seg['id']}] {seg['text_original'][:80]}...")
            
    except Exception as e:
        print(f"❌ Error: {e}")
