#!/usr/bin/env python3
"""
Dictionary Manager
==================
Manages the Arabic spell-check dictionary.
Loads rules from custom_dict.txt and provides lookup methods.
"""

import os
import logging
from pathlib import Path
from typing import Optional
from Levenshtein import distance as levenshtein_distance

logger = logging.getLogger(__name__)


class DictionaryManager:
    """Manages Arabic spelling rules and dictionary lookups."""
    
    def __init__(self, dict_path: Optional[str] = None):
        """
        Initialize the dictionary manager.
        
        Args:
            dict_path: Path to custom dictionary file.
                      If None, looks for custom_dict.txt in same directory.
        """
        if dict_path is None:
            dict_path = str(Path(__file__).parent / "custom_dict.txt")
        
        self.dict_path = dict_path
        self.exact_rules = {}      # Exact match rules: error => correction
        self.word_set = set()      # All known correct words
        self.max_edit_distance = 2  # Max Levenshtein distance for suggestions
        
        self._load_dictionary()
    
    def _load_dictionary(self):
        """Load dictionary from file."""
        if not os.path.exists(self.dict_path):
            logger.warning(f"Dictionary file not found: {self.dict_path}")
            return
        
        with open(self.dict_path, 'r', encoding='utf-8') as f:
            for line_num, line in enumerate(f, 1):
                line = line.strip()
                
                # Skip empty lines and comments
                if not line or line.startswith('#'):
                    continue
                
                # Parse rule: "error => correction"
                if '=>' in line:
                    parts = line.split('=>', 1)
                    error = parts[0].strip()
                    correction = parts[1].strip()
                    
                    if error and correction:
                        self.exact_rules[error] = correction
                        self.word_set.add(correction)
                
                # Parse valid word: "word <=" means this word is correct
                elif '<=' in line:
                    parts = line.split('<=', 1)
                    word = parts[0].strip()
                    if word:
                        self.word_set.add(word)
        
        logger.info(f"Loaded {len(self.exact_rules)} error rules, "
                    f"{len(self.word_set)} known words from {self.dict_path}")
    
    def check_exact(self, word: str) -> Optional[str]:
        """
        Check if word has an exact match rule.
        
        Args:
            word: Word to check
            
        Returns:
            Correction if found, None otherwise
        """
        return self.exact_rules.get(word)
    
    def is_known_word(self, word: str) -> bool:
        """Check if word is in the known word set."""
        return word in self.word_set
    
    def suggest_corrections(self, word: str, max_suggestions: int = 3) -> list:
        """
        Suggest corrections for a word using Levenshtein distance.
        
        Args:
            word: Word to get suggestions for
            max_suggestions: Maximum number of suggestions
            
        Returns:
            List of suggested corrections sorted by distance
        """
        if not word or len(word) < 2:
            return []
        
        suggestions = []
        
        for known_word in self.word_set:
            dist = levenshtein_distance(word, known_word)
            if 0 < dist <= self.max_edit_distance:
                suggestions.append((known_word, dist))
        
        # Sort by distance, then alphabetically
        suggestions.sort(key=lambda x: (x[1], x[0]))
        
        return [s[0] for s in suggestions[:max_suggestions]]
    
    def get_stats(self) -> dict:
        """Get dictionary statistics."""
        return {
            'total_rules': len(self.exact_rules),
            'total_words': len(self.word_set),
            'dict_path': self.dict_path
        }


# Singleton instance
_dict_instance = None

def get_dictionary(dict_path: Optional[str] = None) -> DictionaryManager:
    """Get or create dictionary singleton."""
    global _dict_instance
    if _dict_instance is None:
        _dict_instance = DictionaryManager(dict_path)
    return _dict_instance
