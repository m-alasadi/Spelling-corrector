#!/usr/bin/env python3
"""
Fast Spell Corrector for Large Files
=====================================
Optimized version for handling large ASR files with 100+ segments.

Key optimizations:
- Larger batch sizes (10-20 segments per API call)
- Concurrent API calls using threading
- Streaming progress updates
- Smarter caching with file-based storage
"""

import json
import os
import sys
import hashlib
import logging
import time
from pathlib import Path
from typing import Optional, Generator, Callable
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
from openai import OpenAI
from dotenv import load_dotenv

logger = logging.getLogger(__name__)
load_dotenv()


class FastSpellCorrector:
    """High-performance Arabic spell corrector for large files."""
    
    def __init__(self, api_key: Optional[str] = None, model: str = "gpt-4",
                 batch_size: int = 15, max_workers: int = 3):
        """
        Initialize the fast spell corrector.
        
        Args:
            api_key: OpenAI API key
            model: Model to use (gpt-3.5-turbo is faster/cheaper for large files)
            batch_size: Segments per API call (default: 15, up from 5)
            max_workers: Concurrent API calls (default: 3)
        """
        self.api_key = api_key or os.getenv('OPENAI_API_KEY')
        if not self.api_key:
            raise ValueError("OpenAI API key required")
        
        self.model = model
        self.batch_size = batch_size
        self.max_workers = max_workers
        self.client = OpenAI(api_key=self.api_key)
        self.cache = {}
        self.stats = {
            'total_segments': 0,
            'corrected_segments': 0,
            'cached_segments': 0,
            'errors': 0,
            'batches_processed': 0
        }
    
    def _get_cache_key(self, text: str) -> str:
        return hashlib.md5(text.encode('utf-8')).hexdigest()
    
    def _build_batch_prompt(self, texts: list, language: str = "ar-SA") -> str:
        numbered = "\n".join([f"[{i+1}] {t}" for i, t in enumerate(texts)])
        return f"""أنت مصحح إملائي محترف للغة العربية.

النصوص التالية تحتاج تصحيح إملائي. كل نص مرقم بين [].

النصوص:
{numbered}

تعليمات:
1. صحح الأخطاء الإملائية فقط
2. لا تغير المعنى أو الصياغة
3. حافظ على اللهجة الأصلية
4. أرجع النصوص المصححة فقط بالترتيب [1] [2]...

النصوص المصححة:"""
    
    def _call_api(self, texts: list, language: str) -> list:
        """Make a single API call for a batch of texts."""
        prompt = self._build_batch_prompt(texts, language)
        
        response = self.client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": "أنت مصحح إملائي محترف للنصوص العربية."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.1,
            max_tokens=4096,
            top_p=1.0,
        )
        
        result_text = response.choices[0].message.content.strip()
        return self._parse_batch_result(result_text, len(texts))
    
    def _parse_batch_result(self, result_text: str, expected_count: int) -> list:
        import re
        corrected = []
        
        pattern = r'\[(\d+)\]\s*(.*?)(?=\[\d+\]|$)'
        matches = re.findall(pattern, result_text, re.DOTALL)
        
        if matches:
            for num, text in matches:
                corrected.append(text.strip())
        
        if len(corrected) != expected_count:
            lines = [l.strip() for l in result_text.split('\n') if l.strip()]
            cleaned = [re.sub(r'^\[\d+\]\s*', '', re.sub(r'^\d+\.\s*', '', l)) for l in lines]
            corrected = [c for c in cleaned if c]
        
        while len(corrected) < expected_count:
            corrected.append("")
        
        return corrected[:expected_count]
    
    def correct_large_file(self, data: dict, progress_callback: Optional[Callable] = None) -> dict:
        """
        Process a large file with optimized performance.
        
        Args:
            data: Input data dictionary with segments
            progress_callback: Function called with (current, total, message)
            
        Returns:
            Updated data with corrections
        """
        start_time = time.time()
        segments = data.get('segments', [])
        language = data.get('language', 'ar-SA')
        
        self.stats['total_segments'] = len(segments)
        
        # Separate texts that need correction
        texts_to_correct = []
        indices_to_correct = []
        
        for i, seg in enumerate(segments):
            text = seg.get('text_original', '')
            if not text or not text.strip():
                seg['text_corrected'] = text
                continue
            
            # Check cache
            cache_key = self._get_cache_key(text)
            if cache_key in self.cache:
                seg['text_corrected'] = self.cache[cache_key]
                self.stats['cached_segments'] += 1
                continue
            
            texts_to_correct.append(text)
            indices_to_correct.append(i)
        
        total_to_correct = len(texts_to_correct)
        logger.info(f"Total: {len(segments)} segments, {total_to_correct} to correct, {self.stats['cached_segments']} cached")
        
        if progress_callback:
            progress_callback(0, total_to_correct, f"بدء التصحيح... {total_to_correct} مقطع")
        
        # Create batches
        batches = []
        for start in range(0, total_to_correct, self.batch_size):
            batch = texts_to_correct[start:start + self.batch_size]
            batch_indices = indices_to_correct[start:start + self.batch_size]
            batches.append((batch, batch_indices))
        
        # Process batches concurrently
        processed = 0
        
        def process_batch(batch_data):
            batch_texts, batch_indices = batch_data
            try:
                results = self._call_api(batch_texts, language)
                return batch_indices, results, None
            except Exception as e:
                logger.error(f"Batch error: {e}")
                return batch_indices, batch_texts, str(e)
        
        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            futures = {executor.submit(process_batch, b): b for b in batches}
            
            for future in as_completed(futures):
                indices, results, error = future.result()
                
                if error:
                    self.stats['errors'] += len(indices)
                    # Keep original on error
                    for idx, text in zip(indices, results):
                        segments[idx]['text_corrected'] = text
                else:
                    for idx, corrected in zip(indices, results):
                        segments[idx]['text_corrected'] = corrected
                        self.stats['corrected_segments'] += 1
                        # Cache
                        cache_key = self._get_cache_key(segments[idx]['text_original'])
                        self.cache[cache_key] = corrected
                
                processed += len(indices)
                self.stats['batches_processed'] += 1
                
                if progress_callback:
                    progress_callback(
                        processed, total_to_correct,
                        f"تم {processed}/{total_to_correct} مقطع"
                    )
        
        elapsed = time.time() - start_time
        self.stats['duration_seconds'] = round(elapsed, 2)
        
        logger.info(f"Completed in {elapsed:.1f}s | Corrected: {self.stats['corrected_segments']} | Errors: {self.stats['errors']}")
        
        return data
    
    def get_stats(self) -> dict:
        return self.stats.copy()


def get_fast_corrector(model: str = "gpt-3.5-turbo") -> FastSpellCorrector:
    """
    Factory function to get a fast corrector.
    
    For large files, gpt-3.5-turbo is recommended:
    - 3-5x faster than GPT-4
    - 10-20x cheaper
    - Good enough for spelling correction
    """
    return FastSpellCorrector(model=model, batch_size=15, max_workers=3)
