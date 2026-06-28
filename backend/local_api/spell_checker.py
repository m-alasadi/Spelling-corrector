#!/usr/bin/env python3
"""
Spell Checker Engine — Optimized v2
====================================
Hybrid spell checker with 4 enterprise optimizations:
  1. Pre-Filtering  — skip noise/symbols before AI
  2. Semantic Cache — SQLite-backed cache (0 cost for repeats)
  3. Rate Limiting  — Semaphore prevents HTTP 429
  4. Smart Batching — skip already-corrected segments

Flow:
  Text → Pre-Filter → Cache Check → Dict Check → AI (if needed) → Word Diff → Result
"""

import os
import re
import json
import time
import hashlib
import sqlite3
import logging
from typing import Optional, Callable
from pathlib import Path
from threading import Lock

from openai import OpenAI
from dotenv import load_dotenv

from dictionary import get_dictionary

logger = logging.getLogger(__name__)
load_dotenv()


# ══════════════════════════════════════════════════════════════
# 1. PRE-FILTER: Skip noise/symbols/emojis before AI
# ══════════════════════════════════════════════════════════════

# Patterns to skip (no Arabic words → no spelling errors)
_NOISE_PATTERNS = [
    re.compile(r'^[\d\s\.\,\;\:\-\+\=\(\)\[\]\{\}\/\\@#\$%\^&\*\<\>\|~`\'\"]+$'),  # numbers/symbols only
    re.compile(r'^\[[\w\s\u0600-\u06FF]+\]$'),           # [موسيقى], [ضحك]
    re.compile(r'^\([\w\s\u0600-\u06FF]+\)$'),           # (تصفيق), ( laughing )
    re.compile(r'^[\s]*$'),                                # empty/whitespace
    re.compile(r'^[\U0001F600-\U0001F9FF\u2600-\u26FF\u2700-\u27BF]+$'),  # emojis
    re.compile(r'^[\d]+[\.\,\:\/\-]*[\d]*[\.\,\:\/\-]*[\d]*$'),  # timestamps 00:05:32
    re.compile(r'^[\-=_]{3,}$'),                           # separators  ---
]


def should_skip_ai(text: str) -> bool:
    """
    Check if a text segment should skip AI correction.
    Returns True if the segment is noise/symbols/numbers.
    """
    if not text or not text.strip():
        return True

    stripped = text.strip()

    # Check against noise patterns
    for pattern in _NOISE_PATTERNS:
        if pattern.match(stripped):
            return True

    # Check if there are ANY Arabic characters
    arabic_chars = re.findall(r'[\u0600-\u06FF\u0750-\u077F\u08A0-\u08FF\uFB50-\uFDFF\uFE70-\uFEFF]', stripped)
    if len(arabic_chars) < 2:
        return True  # Less than 2 Arabic chars → not worth correcting

    return False


# ══════════════════════════════════════════════════════════════
# 2. SEMANTIC CACHE: SQLite-backed persistent cache
# ══════════════════════════════════════════════════════════════

class SemanticCache:
    """
    SQLite-backed cache for spell corrections.
    Stores text_hash → corrected_text mappings.
    Thread-safe with Lock.
    """

    def __init__(self, db_path: Optional[str] = None):
        if db_path is None:
            db_path = str(Path(__file__).parent / "cache.db")

        self.db_path = db_path
        self.lock = Lock()
        self.memory_cache = {}  # In-memory L1 cache for hot data
        self._init_db()

    def _init_db(self):
        """Create table if not exists."""
        with self.lock:
            conn = sqlite3.connect(self.db_path)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS corrections (
                    text_hash TEXT PRIMARY KEY,
                    original TEXT NOT NULL,
                    corrected TEXT NOT NULL,
                    model TEXT DEFAULT '',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            conn.commit()
            conn.close()
        logger.info(f"Cache initialized: {self.db_path}")

    def _hash(self, text: str) -> str:
        """Generate MD5 hash for text."""
        return hashlib.md5(text.encode('utf-8')).hexdigest()

    def get(self, text: str) -> Optional[str]:
        """Lookup cached correction. Returns None if not found."""
        h = self._hash(text)

        # L1: In-memory cache
        if h in self.memory_cache:
            return self.memory_cache[h]

        # L2: SQLite
        with self.lock:
            conn = sqlite3.connect(self.db_path)
            row = conn.execute(
                "SELECT corrected FROM corrections WHERE text_hash = ?", (h,)
            ).fetchone()
            conn.close()

        if row:
            self.memory_cache[h] = row[0]  # Promote to L1
            return row[0]

        return None

    def set(self, text: str, corrected: str, model: str = ""):
        """Store a correction in cache."""
        h = self._hash(text)

        # L1: In-memory
        self.memory_cache[h] = corrected

        # L2: SQLite
        with self.lock:
            conn = sqlite3.connect(self.db_path)
            conn.execute(
                "INSERT OR REPLACE INTO corrections (text_hash, original, corrected, model) VALUES (?, ?, ?, ?)",
                (h, text, corrected, model)
            )
            conn.commit()
            conn.close()

    def stats(self) -> dict:
        """Get cache statistics."""
        with self.lock:
            conn = sqlite3.connect(self.db_path)
            total = conn.execute("SELECT COUNT(*) FROM corrections").fetchone()[0]
            conn.close()
        return {
            'total_cached': total,
            'memory_cached': len(self.memory_cache),
            'db_path': self.db_path,
        }


# ══════════════════════════════════════════════════════════════
# Text Tokenizer
# ══════════════════════════════════════════════════════════════

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


# ══════════════════════════════════════════════════════════════
# Word-Level Diff
# ══════════════════════════════════════════════════════════════

def compute_word_diff(original: str, corrected: str) -> list:
    """
    Compare original and corrected text word-by-word.
    Returns list of tokens with correction info.
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
                for offset in range(orig_count):
                    corrections[i1 + offset] = {
                        'is_error': True,
                        'suggestion': corr_words[j1 + offset]
                    }
            else:
                corrections[i1] = {'is_error': True, 'suggestion': corr_text}
                for k in range(i1 + 1, i2):
                    corrections[k] = {'is_error': True, 'suggestion': None, 'merged': True}

        elif op == 'delete':
            for k in range(i1, i2):
                corrections[k] = {'is_error': True, 'suggestion': ''}

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


# ══════════════════════════════════════════════════════════════
# Spell Checker Class (Optimized)
# ══════════════════════════════════════════════════════════════

class SpellChecker:
    """
    Hybrid spell checker with enterprise optimizations:
      - Pre-filtering: skip noise/symbols
      - Semantic caching: SQLite-backed
      - Rate limiting: semaphore on API calls
      - Smart batching: skip already-corrected
    """

    def __init__(self, model: str = "gpt-4o-mini"):
        api_key = os.getenv('OPENAI_API_KEY')
        if not api_key:
            logger.warning("No OPENAI_API_KEY found. AI corrections disabled.")
            self.client = None
        else:
            self.client = OpenAI(api_key=api_key)

        self.model = model
        self.dict = get_dictionary()
        self.cache = SemanticCache()
        self.stats = {
            'total_segments': 0,
            'dict_corrections': 0,
            'ai_corrections': 0,
            'cache_hits': 0,
            'filtered_noise': 0,
            'api_calls': 0,
            'api_errors': 0,
        }

    # ── Prompt Builder (Optimized) ──
    def _build_ai_prompt(self, texts: list, language: str = "ar") -> str:
        """Build batch correction prompt — minimal tokens."""
        numbered = "\n".join([f"[{i+1}] {t}" for i, t in enumerate(texts)])
        return f"""صحح الأخطاء الإملائية:
{numbered}

القواعد: صحح الإملاء فقط، لا تغير المعنى، أرجع بالترتيب [1] [2]...
النصوص المصححة:"""

    # ── AI Call with Retry ──
    def _call_ai_batch(self, texts: list, language: str = "ar") -> list:
        """Call OpenAI API with retry and exponential backoff."""
        if not self.client:
            return texts

        prompt = self._build_ai_prompt(texts, language)

        for attempt in range(3):
            try:
                response = self.client.chat.completions.create(
                    model=self.model,
                    messages=[
                        {"role": "system", "content": "مصحح إملائي عربي."},
                        {"role": "user", "content": prompt}
                    ],
                    temperature=0.1,
                    max_tokens=2048,
                )

                result_text = response.choices[0].message.content.strip()
                self.stats['api_calls'] += 1
                return self._parse_batch_result(result_text, len(texts))

            except Exception as e:
                self.stats['api_errors'] += 1
                if attempt < 2:
                    time.sleep(2 ** attempt)
                    continue
                logger.error(f"AI API error after {attempt+1} attempts: {e}")
                return texts

    def _parse_batch_result(self, result_text: str, expected: int) -> list:
        """Parse numbered batch result from AI."""
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

    # ── Dictionary Correction ──
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

    # ── Single Segment Correction ──
    def correct_segment(self, text: str, language: str = "ar") -> str:
        """Correct a single segment with all optimizations."""
        if not text or not text.strip():
            return text

        self.stats['total_segments'] += 1

        # 1. Pre-filter: skip noise
        if should_skip_ai(text):
            self.stats['filtered_noise'] += 1
            return text

        # 2. Cache check
        cached = self.cache.get(text)
        if cached is not None:
            self.stats['cache_hits'] += 1
            return cached

        # 3. Dictionary check
        dict_result = self._correct_with_dict(text)

        # 4. AI check (if dict didn't fix it)
        if self.client and dict_result == text:
            ai_result = self._call_ai_batch([text], language)[0]
            if ai_result and ai_result != text:
                self.stats['ai_corrections'] += 1
                self.cache.set(text, ai_result, self.model)
                return ai_result

        # Cache the dict result too
        if dict_result != text:
            self.cache.set(text, dict_result, self.model)

        return dict_result

    # ── Batch Correction (Parallel + Semaphore) ──
    def correct_batch(self, texts: list, language: str = "ar",
                      progress_callback: Optional[Callable] = None) -> list:
        """
        Correct a batch with all optimizations:
        - Pre-filter noise
        - Cache lookup
        - Dictionary first
        - Parallel AI with rate limiting
        """
        import threading
        from concurrent.futures import ThreadPoolExecutor, as_completed

        total = len(texts)
        results = [None] * total
        texts_needing_ai = []
        ai_indices = []

        # ── Phase 1: Filter + Dict + Cache (instant) ──
        for i, text in enumerate(texts):
            if not text or not text.strip():
                results[i] = text
                continue

            self.stats['total_segments'] += 1

            # Pre-filter: skip noise
            if should_skip_ai(text):
                results[i] = text
                self.stats['filtered_noise'] += 1
                continue

            # Cache check
            cached = self.cache.get(text)
            if cached is not None:
                results[i] = cached
                self.stats['cache_hits'] += 1
                continue

            # Dictionary check
            dict_result = self._correct_with_dict(text)
            results[i] = dict_result

            if dict_result == text:
                # Needs AI
                texts_needing_ai.append(text)
                ai_indices.append(i)
            else:
                self.stats['dict_corrections'] += 1
                # Cache dict result
                self.cache.set(text, dict_result, self.model)

        skipped = total - len(texts_needing_ai)
        logger.info(
            f"Pre-filter: {self.stats['filtered_noise']} noise, "
            f"{self.stats['cache_hits']} cached, "
            f"{self.stats['dict_corrections']} dict, "
            f"{len(texts_needing_ai)} need AI (of {total})"
        )

        # ── Phase 2: AI with Rate Limiting ──
        if self.client and texts_needing_ai:
            batch_size = 30
            semaphore = threading.Semaphore(5)  # Max 5 concurrent API calls

            batches = []
            batch_idx_list = []
            for batch_start in range(0, len(texts_needing_ai), batch_size):
                batch = texts_needing_ai[batch_start:batch_start + batch_size]
                batch_indices = ai_indices[batch_start:batch_start + batch_size]
                batches.append(batch)
                batch_idx_list.append(batch_indices)

            def process_batch(args):
                batch, batch_indices = args
                with semaphore:  # Rate limit: max 5 concurrent
                    ai_results = self._call_ai_batch(batch, language)
                return list(zip(batch_indices, ai_results))

            with ThreadPoolExecutor(max_workers=5) as executor:
                futures = [
                    executor.submit(process_batch, (b, bi))
                    for b, bi in zip(batches, batch_idx_list)
                ]

                for future in as_completed(futures):
                    try:
                        batch_results = future.result()
                        for idx, ai_text in batch_results:
                            if ai_text and ai_text != texts[idx]:
                                results[idx] = ai_text
                                self.stats['ai_corrections'] += 1
                                self.cache.set(texts[idx], ai_text, self.model)
                    except Exception as e:
                        logger.error(f"Batch processing error: {e}")

            if progress_callback:
                progress_callback(len(texts_needing_ai), len(texts_needing_ai), "AI complete")

        return results

    # ── Stats ──
    def get_stats(self) -> dict:
        """Get comprehensive statistics."""
        cache_stats = self.cache.stats()
        return {
            **self.stats,
            'cache': cache_stats,
            'tokens_saved_approx': self.stats['cache_hits'] + self.stats['filtered_noise'],
        }


# ── Singleton ──
_checker = None

def get_checker(model: str = "gpt-4o-mini") -> SpellChecker:
    global _checker
    if _checker is None:
        _checker = SpellChecker(model)
    return _checker
