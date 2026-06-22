#!/usr/bin/env python3
"""
Spell Corrector for Arabic ASR Output
=====================================
This module corrects spelling errors in Arabic text produced by ASR systems.

Usage:
    python corrector.py input.json output.json

Rules:
    - Correct spelling only
    - No sentence restructuring
    - No meaning changes
    - Preserve original dialect
    - Never merge segments
    - Never reorder segments
"""

import json
import os
import sys
import hashlib
import logging
from pathlib import Path
from typing import Optional
from datetime import datetime

from openai import OpenAI
from dotenv import load_dotenv

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('corrector.log', encoding='utf-8')
    ]
)
logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv()


class SpellCorrector:
    """Arabic spell corrector using OpenAI API."""
    
    def __init__(self, api_key: Optional[str] = None, model: str = "gpt-4"):
        """
        Initialize the spell corrector.
        
        Args:
            api_key: OpenAI API key. If not provided, reads from OPENAI_API_KEY env var.
            model: Model to use for correction. Default is gpt-4.
        """
        self.api_key = api_key or os.getenv('OPENAI_API_KEY')
        if not self.api_key:
            raise ValueError("OpenAI API key is required. Set OPENAI_API_KEY in .env or pass api_key parameter.")
        
        self.model = model
        self.client = OpenAI(api_key=self.api_key)
        self.cache = {}
        self.stats = {
            'total_segments': 0,
            'corrected_segments': 0,
            'cached_segments': 0,
            'errors': 0
        }
    
    def _get_cache_key(self, text: str) -> str:
        """Generate cache key for text."""
        return hashlib.md5(text.encode('utf-8')).hexdigest()
    
    def _build_prompt(self, text: str, language: str = "ar-SA") -> str:
        """
        Build the correction prompt.
        
        Args:
            text: Text to correct
            language: Language code (default: ar-SA)
            
        Returns:
            Formatted prompt string
        """
        return f"""أنت مصحح إملائي محترف للغة العربية.

النص الأصلي:
{text}

تعليمات صارمة:
1. صحح الأخطاء الإملائية فقط
2. لا تغير المعنى أو الصياغة أو بنية الجملة
3. حافظ على اللهجة الأصلية (فصحى، عامية، إلخ)
4. لا تضيف أو تحذف أي كلمات
5. لا تدمج جملتين في جملة واحدة
6. حافظ على أسماء الأشخاص
7. إذا كنت غير متأكد من كلمة، اتركها كما هي
8. أرجع النص المصحح فقط بدون أي شرح أو تعليق

النص المصحح:"""
    
    def correct_text(self, text: str, language: str = "ar-SA", use_cache: bool = True) -> str:
        """
        Correct spelling in a single text segment.
        
        Args:
            text: Text to correct
            language: Language code
            use_cache: Whether to use caching
            
        Returns:
            Corrected text
        """
        if not text or not text.strip():
            return text
        
        # Check cache
        if use_cache:
            cache_key = self._get_cache_key(text)
            if cache_key in self.cache:
                self.stats['cached_segments'] += 1
                logger.debug(f"Cache hit for text: {text[:50]}...")
                return self.cache[cache_key]
        
        try:
            prompt = self._build_prompt(text, language)
            
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {
                        "role": "system",
                        "content": "أنت مصحح إملائي محترف للنصوص العربية. مهمتك تصحيح الأخطاء الإملائية فقط مع الحفاظ على المعنى وال اللهجة الأصلية."
                    },
                    {
                        "role": "user",
                        "content": prompt
                    }
                ],
                temperature=0.1,  # Low temperature for consistency
                max_tokens=1024,
                top_p=1.0,
                frequency_penalty=0.0,
                presence_penalty=0.0
            )
            
            corrected = response.choices[0].message.content.strip()
            
            # Store in cache
            if use_cache:
                self.cache[cache_key] = corrected
            
            self.stats['corrected_segments'] += 1
            return corrected
            
        except Exception as e:
            logger.error(f"Error correcting text: {e}")
            self.stats['errors'] += 1
            return text  # Return original on error
    
    def correct_batch(self, texts: list, language: str = "ar-SA", use_cache: bool = True) -> list:
        """
        Correct spelling for a batch of texts.
        
        Args:
            texts: List of texts to correct
            language: Language code
            use_cache: Whether to use caching
            
        Returns:
            List of corrected texts
        """
        corrected_texts = []
        for text in texts:
            corrected = self.correct_text(text, language, use_cache)
            corrected_texts.append(corrected)
        return corrected_texts
    
    def _build_batch_prompt(self, texts: list, language: str = "ar-SA") -> str:
        """
        Build a batch correction prompt for multiple segments.
        
        Args:
            texts: List of texts to correct
            language: Language code
            
        Returns:
            Formatted batch prompt string
        """
        numbered_texts = "\n".join([f"[{i+1}] {text}" for i, text in enumerate(texts)])
        
        return f"""أنت مصحح إملائي محترف للغة العربية.

النصوص التالية تحتاج تصحيح إملائي. كل نص مرقم بين قوسين [].

النصوص:
{numbered_texts}

تعليمات صارمة:
1. صحح الأخطاء الإملائية فقط لكل نص
2. لا تغير المعنى أو الصياغة أو بنية الجمل
3. حافظ على اللهجة الأصلية لكل نص
4. لا تضيف أو تحذف أي كلمات
5. لا تدمج نصين في نص واحد
6. حافظ على ترتيب النصوص كما هي
7. أرجع النصوص المصححة فقط بالترتيب نفس الترقيم [1] [2] [3]...

النصوص المصححة:"""
    
    def correct_batch_optimized(self, texts: list, language: str = "ar-SA", 
                                 batch_size: int = 5, use_cache: bool = True) -> list:
        """
        Correct spelling for multiple segments in batches (optimized for API calls).
        This sends multiple segments in one API call, reducing cost and time.
        
        Args:
            texts: List of texts to correct
            language: Language code
            batch_size: Number of segments per API call (default: 5)
            use_cache: Whether to use caching
            
        Returns:
            List of corrected texts (same length as input)
        """
        # Initialize result list with original texts as default
        all_corrected = list(texts)
        
        # Separate texts that need correction
        texts_to_correct = []
        text_indices = []
        
        for i, text in enumerate(texts):
            if not text or not text.strip():
                continue  # Keep empty texts as-is
            
            # Check cache first
            if use_cache:
                cache_key = self._get_cache_key(text)
                if cache_key in self.cache:
                    all_corrected[i] = self.cache[cache_key]
                    self.stats['cached_segments'] += 1
                    continue
            
            # Needs API correction
            texts_to_correct.append(text)
            text_indices.append(i)
        
        logger.info(f"Texts to correct: {len(texts_to_correct)}/{len(texts)} (cached: {len(texts) - len(texts_to_correct)})")
        
        # Process in batches
        for batch_start in range(0, len(texts_to_correct), batch_size):
            batch = texts_to_correct[batch_start:batch_start + batch_size]
            batch_indices = text_indices[batch_start:batch_start + batch_size]
            
            try:
                prompt = self._build_batch_prompt(batch, language)
                
                response = self.client.chat.completions.create(
                    model=self.model,
                    messages=[
                        {
                            "role": "system",
                            "content": "أنت مصحح إملائي محترف للنصوص العربية. مهمتك تصحيح الأخطاء الإملائية فقط مع الحفاظ على المعنى وال اللهجة الأصلية."
                        },
                        {
                            "role": "user",
                            "content": prompt
                        }
                    ],
                    temperature=0.1,
                    max_tokens=2048,
                    top_p=1.0,
                    frequency_penalty=0.0,
                    presence_penalty=0.0
                )
                
                result_text = response.choices[0].message.content.strip()
                
                # Parse the batch result
                corrected_batch = self._parse_batch_result(result_text, len(batch))
                
                # Assign results to correct positions
                for j, (idx, corrected) in enumerate(zip(batch_indices, corrected_batch)):
                    all_corrected[idx] = corrected
                    self.stats['corrected_segments'] += 1
                    
                    # Cache the result
                    if use_cache:
                        cache_key = self._get_cache_key(texts_to_correct[batch_start + j])
                        self.cache[cache_key] = corrected
                
                logger.info(f"Batch processed {len(batch)} segments")
                
            except Exception as e:
                logger.error(f"Error in batch processing: {e}")
                self.stats['errors'] += len(batch)
                # all_corrected already has original texts as fallback
        
        return all_corrected
    
    def _parse_batch_result(self, result_text: str, expected_count: int) -> list:
        """
        Parse batch correction result from API response.
        
        Args:
            result_text: Raw API response text
            expected_count: Expected number of corrected texts
            
        Returns:
            List of corrected texts
        """
        import re
        
        corrected = []
        
        # Try to parse numbered format [1] text [2] text ...
        pattern = r'\[(\d+)\]\s*(.*?)(?=\[\d+\]|$)'
        matches = re.findall(pattern, result_text, re.DOTALL)
        
        if matches:
            for num, text in matches:
                corrected.append(text.strip())
        
        # If parsing failed or incomplete, split by newlines
        if len(corrected) != expected_count:
            lines = [line.strip() for line in result_text.split('\n') if line.strip()]
            # Remove numbering if present
            cleaned_lines = []
            for line in lines:
                cleaned = re.sub(r'^\[\d+\]\s*', '', line)
                cleaned = re.sub(r'^\d+\.\s*', '', cleaned)
                if cleaned:
                    cleaned_lines.append(cleaned)
            corrected = cleaned_lines
        
        # Ensure we have the right number of results
        while len(corrected) < expected_count:
            corrected.append("")
        
        return corrected[:expected_count]
    
    def process_json(self, input_path: str, output_path: str, use_cache: bool = True, 
                     use_batch: bool = True, batch_size: int = 5) -> dict:
        """
        Process a complete ASR JSON file.
        
        Args:
            input_path: Path to input JSON file
            output_path: Path to output JSON file
            use_cache: Whether to use caching
            use_batch: Whether to use batch processing (faster, cheaper)
            batch_size: Number of segments per batch (default: 5)
            
        Returns:
            Processing statistics
        """
        logger.info(f"Processing: {input_path}")
        start_time = datetime.now()
        
        # Read input file
        with open(input_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        # Validate input structure
        if 'segments' not in data:
            raise ValueError("Input JSON must contain 'segments' array")
        
        # Get language from data or default to ar-SA
        language = data.get('language', 'ar-SA')
        
        # Process segments
        segments = data['segments']
        self.stats['total_segments'] = len(segments)
        
        if use_batch:
            # Batch processing mode (faster, fewer API calls)
            logger.info(f"Using batch processing (batch_size={batch_size})")
            
            # Extract texts for batch processing
            texts = []
            valid_indices = []
            
            for i, segment in enumerate(segments):
                if 'text_original' not in segment:
                    logger.warning(f"Segment {i} missing 'text_original' field, skipping")
                    continue
                
                original_text = segment['text_original']
                
                # Keep empty segments as-is
                if not original_text or not original_text.strip():
                    segment['text_corrected'] = original_text
                    continue
                
                texts.append(original_text)
                valid_indices.append(i)
            
            # Batch correct all valid texts
            if texts:
                corrected_texts = self.correct_batch_optimized(
                    texts, language, batch_size, use_cache
                )
                
                # Assign corrected texts back to segments
                for idx, corrected in zip(valid_indices, corrected_texts):
                    segments[idx]['text_corrected'] = corrected
            
            logger.info(f"Batch processing complete")
        else:
            # Individual processing mode (slower, more API calls)
            logger.info("Using individual processing mode")
            
            for i, segment in enumerate(segments):
                if 'text_original' not in segment:
                    logger.warning(f"Segment {i} missing 'text_original' field, skipping")
                    continue
                
                original_text = segment['text_original']
                
                # Skip empty segments
                if not original_text or not original_text.strip():
                    segment['text_corrected'] = original_text
                    continue
                
                # Correct the text
                corrected_text = self.correct_text(original_text, language, use_cache)
                segment['text_corrected'] = corrected_text
                
                # Log progress every 10 segments
                if (i + 1) % 10 == 0:
                    logger.info(f"Processed {i + 1}/{len(segments)} segments")
        
        # Ensure output directory exists
        output_dir = Path(output_path).parent
        output_dir.mkdir(parents=True, exist_ok=True)
        
        # Write output file
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        
        # Calculate statistics
        end_time = datetime.now()
        duration = (end_time - start_time).total_seconds()
        
        self.stats['duration_seconds'] = duration
        self.stats['input_file'] = input_path
        self.stats['output_file'] = output_path
        
        logger.info(f"Completed in {duration:.2f} seconds")
        logger.info(f"Stats: {json.dumps(self.stats, indent=2)}")
        
        return self.stats
    
    def get_stats(self) -> dict:
        """Get processing statistics."""
        return self.stats.copy()


def main():
    """Main entry point for command line usage."""
    if len(sys.argv) != 3:
        print("Usage: python corrector.py input.json output.json")
        print("\nExample:")
        print("  python corrector.py asr_output.json corrected_output.json")
        sys.exit(1)
    
    input_path = sys.argv[1]
    output_path = sys.argv[2]
    
    # Validate input file exists
    if not os.path.exists(input_path):
        print(f"Error: Input file not found: {input_path}")
        sys.exit(1)
    
    try:
        # Initialize corrector
        corrector = SpellCorrector()
        
        # Process the file
        stats = corrector.process_json(input_path, output_path)
        
        print(f"\n✅ Successfully processed!")
        print(f"   Input:  {stats['input_file']}")
        print(f"   Output: {stats['output_file']}")
        print(f"   Total segments: {stats['total_segments']}")
        print(f"   Corrected: {stats['corrected_segments']}")
        print(f"   Cached: {stats['cached_segments']}")
        print(f"   Duration: {stats['duration_seconds']:.2f}s")
        
    except ValueError as e:
        print(f"Configuration error: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"Error: {e}")
        logger.exception("Unexpected error")
        sys.exit(1)


if __name__ == "__main__":
    main()
