#!/usr/bin/env python3
"""
Spell Checker Engine
====================
Hybrid spell checker combining:
  1. Local dictionary (fast, free)
  2. OpenAI API (intelligent, accurate)

Flow:
  Text → Tokenize → Dictionary Check → AI Check (if needed) → Word Diff → Result
"""

import os
import re
import json
import time
import hashlib
import logging
from typing import Optional, Callable
from pathlib import Path

from openai import OpenAI
from dotenv import load_dotenv

from dictionary import get_dictionary

logger = logging.getLogger(__name__)
load_dotenv()


# ──────────────────────────────────────────────────────────────
# Text Tokenizer
# ──────────────────────────────────────────────────────────────

def tokenize_arabic(text: str) -> list:
    """
    Tokenize Arabic text preserving whitespace and punctuation.
    Returns: [{'type': 'word'|'space'|'punct', 'value': str}, ...]
    """
    tokens = []
    arabic_re = r'[\u0600-\u06FF\u0750-\u077F\u08A0-\u08FF\uFB50-\uFDFF\uFE70-\uFEFF]+'
    
    for match in re.finditer(rf'{arabic_re}|\s+|[^\s{arabic_re[1:-1]}]+', text):
        val = match.group()
        if val.isspace():
            tokens.append({'type': 'space', 'value': val})
        elif re.match(arabic_re, val):
            tokens.append({'type': 'word', 'value': val})
        else:
            tokens.append({'type': 'punct', 'value': val})
    return tokens


# ──────────────────────────────────────────────────────────────
# Word-Level Diff
# ──────────────────────────────────────────────────────────────

def compute_word_diff(original: str, corrected: str) -> list:
    """
    Compare original and corrected text word-by-word.
    Returns list of tokens with correction info:
      {'type', 'value', 'is_error', 'suggestion'}
    
    Key fix: only the FIRST word in a replacement range gets the suggestion.
    Subsequent words in the range are marked as "merged" (consumed by the fix).
    This prevents duplication when accepting corrections.
    """
    import difflib

    if not original or not original.strip():
        return [{'type': 'word', 'value': original or '', 'is_error': False, 'suggestion': None}]

    orig_tokens_full = tokenize_arabic(original)
    corr_tokens_full = tokenize_arabic(corrected)
    
    orig_words = [t['value'] for t in orig_tokens_full if t['type'] == 'word']
    corr_words = [t['value'] for t in corr_tokens_full if t['type'] == 'word']

    matcher = difflib.SequenceMatcher(None, orig_words, corr_words, autojunk=False)

    corrections = {}
    for op, i1, i2, j1, j2 in matcher.get_opcodes():
        if op == 'equal':
            for k in range(i1, i2):
                corrections[k] = {'is_error': False, 'suggestion': None}
        
        elif op == 'replace':
            corr_text = ' '.join(corr_words[j1:j2])
            orig_count = i2 - i1
            corr_count = j2 - j1
            
            if orig_count == corr_count:
                # 1-to-1 replacement: each word maps to its correction
                for offset in range(orig_count):
                    corrections[i1 + offset] = {
                        'is_error': True,
                        'suggestion': corr_words[j1 + offset]
                    }
            else:
                # Many-to-one or one-to-many: first word gets full suggestion,
                # rest are marked as "merged" (consumed)
                corrections[i1] = {
                    'is_error': True,
                    'suggestion': corr_text
                }
                for k in range(i1 + 1, i2):
                    corrections[k] = {
                        'is_error': True,
                        'suggestion': None,  # merged into the first word
                        'merged': True
                    }
        
        elif op == 'delete':
            for k in range(i1, i2):
                corrections[k] = {'is_error': True, 'suggestion': ''}
        
        elif op == 'insert':
            # Insertions are handled by the previous replace/delete
            pass

    result = []
    word_idx = 0
    for token in orig_tokens_full:
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
# Spell Checker Class
# ──────────────────────────────────────────────────────────────

class SpellChecker:
    """
    Hybrid spell checker:
      - Phase 1: Local dictionary (instant, free)
      - Phase 2: OpenAI API (for words not caught by dictionary)
    """
    
    def __init__(self, model: str = "gpt-4o-mini"):
        """
        Args:
            model: OpenAI model to use (gpt-4o-mini is fast & cheap)
        """
        api_key = os.getenv('OPENAI_API_KEY')
        if not api_key:
            logger.warning("No OPENAI_API_KEY found. AI corrections disabled.")
            self.client = None
        else:
            self.client = OpenAI(api_key=api_key)
        
        self.model = model
        self.dict = get_dictionary()
        self.cache = {}
        self.stats = {
            'total_words': 0,
            'dict_corrections': 0,
            'ai_corrections': 0,
            'unknown_words': 0,
            'cached': 0,
            'api_calls': 0,
        }
    
    def _cache_key(self, text: str) -> str:
        return hashlib.md5(text.encode('utf-8')).hexdigest()
    
    def _build_ai_prompt(self, texts: list, language: str = "ar") -> str:
        """Build batch correction prompt for OpenAI."""
        numbered = "\n".join([f"[{i+1}] {t}" for i, t in enumerate(texts)])
        return f"""أنت مصحح إملائي محترف للغة العربية.

النصوص التالية تحتاج تصحيح إملائي. كل نص مرقم بين [].

النصوص:
{numbered}

تعليمات صارمة:
1. صحح الأخطاء الإملائية فقط
2. لا تغير المعنى أو الصياغة
3. حافظ على اللهجة الأصلية
4. لا تضيف أو تحذف كلمات
5. أرجع النصوص المصححة فقط بالترتيب [1] [2]...

النصوص المصححة:"""
    
    def _call_ai_batch(self, texts: list, language: str = "ar") -> list:
        """Call OpenAI API for a batch of texts."""
        if not self.client:
            return texts  # Return as-is if no API key
        
        prompt = self._build_ai_prompt(texts, language)
        
        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": "أنت مصحح إملائي محترف للنصوص العربية."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.1,
                max_tokens=4096,
            )
            
            result_text = response.choices[0].message.content.strip()
            self.stats['api_calls'] += 1
            
            return self._parse_batch_result(result_text, len(texts))
            
        except Exception as e:
            logger.error(f"AI API error: {e}")
            return texts  # Return originals on error
    
    def _parse_batch_result(self, result_text: str, expected: int) -> list:
        """Parse numbered batch result from AI."""
        import re
        corrected = []
        pattern = r'\[(\d+)\]\s*(.*?)(?=\[\d+\]|$)'
        matches = re.findall(pattern, result_text, re.DOTALL)
        
        if matches:
            for num, text in matches:
                corrected.append(text.strip())
        
        if len(corrected) != expected:
            lines = [l.strip() for l in result_text.split('\n') if l.strip()]
            cleaned = [re.sub(r'^\[\d+\]\s*', '', re.sub(r'^\d+\.\s*', '', l)) for l in lines]
            corrected = [c for c in cleaned if c]
        
        while len(corrected) < expected:
            corrected.append("")
        
        return corrected[:expected]
    
    def correct_segment(self, text: str, language: str = "ar") -> str:
        """
        Correct a single text segment using hybrid approach.
        
        Returns: corrected text
        """
        if not text or not text.strip():
            return text
        
        # Check cache
        key = self._cache_key(text)
        if key in self.cache:
            self.stats['cached'] += 1
            return self.cache[key]
        
        # Phase 1: Local dictionary check
        dict_corrected = self._correct_with_dict(text)
        
        # Phase 2: AI check (for remaining errors)
        if self.client and dict_corrected == text:
            # No dict corrections found — try AI
            ai_result = self._call_ai_batch([text], language)[0]
            if ai_result and ai_result != text:
                self.stats['ai_corrections'] += 1
                self.cache[key] = ai_result
                return ai_result
        
        self.cache[key] = dict_corrected
        return dict_corrected
    
    def _correct_with_dict(self, text: str) -> str:
        """Apply dictionary corrections to text."""
        tokens = tokenize_arabic(text)
        result_tokens = []
        changed = False
        
        for token in tokens:
            if token['type'] == 'word':
                correction = self.dict.check_exact(token['value'])
                if correction:
                    result_tokens.append({'type': 'word', 'value': correction})
                    changed = True
                    self.stats['dict_corrections'] += 1
                else:
                    result_tokens.append(token)
            else:
                result_tokens.append(token)
        
        if not changed:
            return text
        
        return ''.join(t['value'] for t in result_tokens)
    
    def correct_batch(self, texts: list, language: str = "ar",
                      progress_callback: Optional[Callable] = None) -> list:
        """
        Correct a batch of text segments.
        
        Args:
            texts: List of text strings
            language: Language code
            progress_callback: fn(current, total, message)
            
        Returns: List of corrected texts
        """
        total = len(texts)
        results = []
        texts_needing_ai = []
        ai_indices = []
        
        # Phase 1: Dictionary for all
        for i, text in enumerate(texts):
            if not text or not text.strip():
                results.append(text)
                continue
            
            dict_result = self._correct_with_dict(text)
            results.append(dict_result)
            
            if dict_result == text:
                # Dictionary didn't fix it — needs AI
                texts_needing_ai.append(text)
                ai_indices.append(i)
            else:
                self.stats['dict_corrections'] += 1
        
        # Phase 2: AI for remaining (in batches of 10)
        if self.client and texts_needing_ai:
            batch_size = 10
            for batch_start in range(0, len(texts_needing_ai), batch_size):
                batch = texts_needing_ai[batch_start:batch_start + batch_size]
                batch_indices = ai_indices[batch_start:batch_start + batch_size]
                
                ai_results = self._call_ai_batch(batch, language)
                
                for idx, ai_text in zip(batch_indices, ai_results):
                    if ai_text and ai_text != texts[idx]:
                        results[idx] = ai_text
                        self.stats['ai_corrections'] += 1
                        self.cache[self._cache_key(texts[idx])] = ai_text
                
                if progress_callback:
                    done = batch_start + len(batch)
                    progress_callback(done, len(texts_needing_ai), f"AI: {done}/{len(texts_needing_ai)}")
        
        return results
    
    def get_stats(self) -> dict:
        """Get correction statistics."""
        return dict(self.stats)


# ──────────────────────────────────────────────────────────────
# Singleton
# ──────────────────────────────────────────────────────────────

_checker = None

def get_checker(model: str = "gpt-4o-mini") -> SpellChecker:
    global _checker
    if _checker is None:
        _checker = SpellChecker(model)
    return _checker
