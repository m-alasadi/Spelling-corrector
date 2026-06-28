#!/usr/bin/env python3
"""
Dictionary Manager — Dynamic v2
================================
Manages the Arabic spell-check dictionary.
Supports dynamic reloading without server restart.

Features:
  - Load from custom_dict.txt
  - Add words dynamically (POST /api/dictionary/add)
  - Reload in-memory dictionary on change
  - Levenshtein-based suggestions
"""

import os
import logging
import threading
from pathlib import Path
from typing import Optional
from Levenshtein import distance as levenshtein_distance

logger = logging.getLogger(__name__)


class DictionaryManager:
    """Manages Arabic spelling rules with dynamic reload support."""

    def __init__(self, dict_path: Optional[str] = None):
        if dict_path is None:
            dict_path = str(Path(__file__).parent / "custom_dict.txt")

        self.dict_path = dict_path
        self.exact_rules = {}      # error => correction
        self.word_set = set()      # all known correct words
        self.max_edit_distance = 2
        self.lock = threading.Lock()
        self._last_modified = 0

        self._load_dictionary()

    def _load_dictionary(self):
        """Load dictionary from file."""
        with self.lock:
            self.exact_rules.clear()
            self.word_set.clear()

            if not os.path.exists(self.dict_path):
                logger.warning(f"Dictionary file not found: {self.dict_path}")
                return

            try:
                self._last_modified = os.path.getmtime(self.dict_path)
            except OSError:
                pass

            with open(self.dict_path, 'r', encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith('#'):
                        continue

                    if '=>' in line:
                        parts = line.split('=>', 1)
                        error = parts[0].strip()
                        correction = parts[1].strip()
                        if error and correction:
                            self.exact_rules[error] = correction
                            self.word_set.add(correction)
                    elif '<=' in line:
                        parts = line.split('<=', 1)
                        word = parts[0].strip()
                        if word:
                            self.word_set.add(word)

            logger.info(
                f"Loaded {len(self.exact_rules)} error rules, "
                f"{len(self.word_set)} known words"
            )

    def reload(self):
        """Force reload dictionary from file."""
        self._load_dictionary()

    def check_if_reloaded(self):
        """Check if file changed and reload if needed."""
        try:
            current_mtime = os.path.getmtime(self.dict_path)
            if current_mtime > self._last_modified:
                logger.info("Dictionary file changed, reloading...")
                self._load_dictionary()
        except OSError:
            pass

    def add_word(self, word: str, correction: Optional[str] = None) -> bool:
        """
        Add a word to the dictionary dynamically.
        If correction is provided: adds as error => correction rule
        If correction is None: adds as known correct word
        Returns True if added successfully.
        """
        word = word.strip()
        if not word:
            return False

        with self.lock:
            if correction:
                # Add as error correction rule
                correction = correction.strip()
                self.exact_rules[word] = correction
                self.word_set.add(correction)
                line = f"{word} => {correction}\n"
            else:
                # Add as known correct word
                self.word_set.add(word)
                line = f"{word} <= {word}\n"

            # Append to file
            try:
                with open(self.dict_path, 'a', encoding='utf-8') as f:
                    f.write(line)
                self._last_modified = os.path.getmtime(self.dict_path)
                logger.info(f"Added to dictionary: {line.strip()}")
                return True
            except Exception as e:
                logger.error(f"Failed to add word to dictionary: {e}")
                return False

    def check_exact(self, word: str) -> Optional[str]:
        """Check if word has an exact match rule."""
        self.check_if_reloaded()
        return self.exact_rules.get(word)

    def is_known_word(self, word: str) -> bool:
        """Check if word is in the known word set."""
        self.check_if_reloaded()
        return word in self.word_set

    def suggest_corrections(self, word: str, max_suggestions: int = 3) -> list:
        """Suggest corrections using Levenshtein distance."""
        if not word or len(word) < 2:
            return []

        suggestions = []
        for known_word in self.word_set:
            dist = levenshtein_distance(word, known_word)
            if 0 < dist <= self.max_edit_distance:
                suggestions.append((known_word, dist))

        suggestions.sort(key=lambda x: (x[1], x[0]))
        return [s[0] for s in suggestions[:max_suggestions]]

    def get_stats(self) -> dict:
        """Get dictionary statistics."""
        return {
            'total_rules': len(self.exact_rules),
            'total_words': len(self.word_set),
            'dict_path': self.dict_path,
        }

    def get_all_words(self) -> list:
        """Get all words in dictionary (for API)."""
        return sorted(list(self.word_set))


# ── Singleton ──
_dict_instance = None

def get_dictionary(dict_path: Optional[str] = None) -> DictionaryManager:
    global _dict_instance
    if _dict_instance is None:
        _dict_instance = DictionaryManager(dict_path)
    return _dict_instance
