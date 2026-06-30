#!/usr/bin/env python3
"""
Error Database
==============
SQLite database for tracking spelling corrections.
Learned from user corrections and AI results.

Features:
  - Track all corrections (AI + user manual)
  - Frequency counting for common errors
  - Auto-expand dictionary from frequent errors
"""

import sqlite3
import logging
import threading
from pathlib import Path
from datetime import datetime
from typing import Optional

logger = logging.getLogger(__name__)


class ErrorDatabase:
    """SQLite database for tracking spelling corrections."""

    def __init__(self, db_path: Optional[str] = None):
        if db_path is None:
            db_path = str(Path(__file__).parent / "corrections.db")

        self.db_path = db_path
        self.lock = threading.Lock()
        self._init_db()

    def _init_db(self):
        """Create tables if not exists."""
        with self.lock:
            conn = sqlite3.connect(self.db_path)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS corrections (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    original TEXT NOT NULL,
                    corrected TEXT NOT NULL,
                    context TEXT DEFAULT '',
                    source TEXT DEFAULT 'ai',
                    frequency INTEGER DEFAULT 1,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(original, corrected)
                )
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_original ON corrections(original)
            """)
            conn.commit()
            conn.close()
        logger.info(f"Error database initialized: {self.db_path}")

    def save_correction(
        self,
        original: str,
        corrected: str,
        context: str = "",
        source: str = "ai"
    ) -> bool:
        """
        Save a correction to the database.
        If the same (original, corrected) pair exists, increment frequency.
        """
        original = original.strip()
        corrected = corrected.strip()
        if not original or not corrected or original == corrected:
            return False

        with self.lock:
            try:
                conn = sqlite3.connect(self.db_path)
                
                # Check if exists
                existing = conn.execute(
                    "SELECT id, frequency FROM corrections WHERE original = ? AND corrected = ?",
                    (original, corrected)
                ).fetchone()
                
                if existing:
                    # Increment frequency
                    conn.execute(
                        "UPDATE corrections SET frequency = frequency + 1, source = ? WHERE id = ?",
                        (source, existing[0])
                    )
                else:
                    # Insert new
                    conn.execute(
                        "INSERT INTO corrections (original, corrected, context, source) VALUES (?, ?, ?, ?)",
                        (original, corrected, context, source)
                    )
                
                conn.commit()
                conn.close()
                return True
            except Exception as e:
                logger.error(f"Failed to save correction: {e}")
                return False

    def get_common_errors(self, min_frequency: int = 2, limit: int = 100) -> list:
        """Get most common errors for dictionary expansion."""
        with self.lock:
            conn = sqlite3.connect(self.db_path)
            rows = conn.execute(
                """SELECT original, corrected, frequency 
                   FROM corrections 
                   WHERE frequency >= ? 
                   ORDER BY frequency DESC 
                   LIMIT ?""",
                (min_frequency, limit)
            ).fetchall()
            conn.close()
        return [{'original': r[0], 'corrected': r[1], 'frequency': r[2]} for r in rows]

    def get_corrections_for_word(self, word: str) -> list:
        """Get all corrections for a specific word."""
        with self.lock:
            conn = sqlite3.connect(self.db_path)
            rows = conn.execute(
                "SELECT corrected, frequency, source FROM corrections WHERE original = ? ORDER BY frequency DESC",
                (word,)
            ).fetchall()
            conn.close()
        return [{'corrected': r[0], 'frequency': r[1], 'source': r[2]} for r in rows]

    def get_stats(self) -> dict:
        """Get database statistics."""
        with self.lock:
            conn = sqlite3.connect(self.db_path)
            total = conn.execute("SELECT COUNT(*) FROM corrections").fetchone()[0]
            total_freq = conn.execute("SELECT SUM(frequency) FROM corrections").fetchone()[0] or 0
            user_count = conn.execute("SELECT COUNT(*) FROM corrections WHERE source = 'user'").fetchone()[0]
            ai_count = conn.execute("SELECT COUNT(*) FROM corrections WHERE source = 'ai'").fetchone()
            ai_count = ai_count[0] if ai_count else 0
            conn.close()
        
        return {
            'total_rules': total,
            'total_frequency': total_freq,
            'user_corrections': user_count,
            'ai_corrections': ai_count,
            'db_path': self.db_path,
        }

    def get_all_corrections(self, limit: int = 1000) -> list:
        """Get all corrections (for export)."""
        with self.lock:
            conn = sqlite3.connect(self.db_path)
            rows = conn.execute(
                "SELECT original, corrected, context, source, frequency, created_at FROM corrections ORDER BY frequency DESC LIMIT ?",
                (limit,)
            ).fetchall()
            conn.close()
        
        return [
            {
                'original': r[0],
                'corrected': r[1],
                'context': r[2],
                'source': r[3],
                'frequency': r[4],
                'created_at': r[5],
            }
            for r in rows
        ]


# Singleton
_db_instance = None

def get_error_db(db_path: Optional[str] = None) -> ErrorDatabase:
    global _db_instance
    if _db_instance is None:
        _db_instance = ErrorDatabase(db_path)
    return _db_instance
