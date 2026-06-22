#!/usr/bin/env python3
"""
Test script for Spell Corrector
================================
This script tests the basic functionality of the spell corrector.
"""

import json
import os
import sys
from pathlib import Path

# Add current directory to path
sys.path.insert(0, str(Path(__file__).parent))

def test_import():
    """Test if module can be imported."""
    try:
        from corrector import SpellCorrector
        print("✅ Module imported successfully")
        return True
    except ImportError as e:
        print(f"❌ Import error: {e}")
        return False

def test_json_structure():
    """Test JSON file structure."""
    test_file = Path(__file__).parent / "test_input.json"
    
    if not test_file.exists():
        print("❌ Test input file not found")
        return False
    
    try:
        with open(test_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        # Check required fields
        required_fields = ['job_id', 'source_file', 'language', 'segments']
        for field in required_fields:
            if field not in data:
                print(f"❌ Missing required field: {field}")
                return False
        
        # Check segments structure
        if not isinstance(data['segments'], list):
            print("❌ 'segments' must be a list")
            return False
        
        for i, segment in enumerate(data['segments']):
            if 'text_original' not in segment:
                print(f"❌ Segment {i} missing 'text_original'")
                return False
        
        print(f"✅ JSON structure valid ({len(data['segments'])} segments)")
        return True
        
    except json.JSONDecodeError as e:
        print(f"❌ Invalid JSON: {e}")
        return False

def test_env_file():
    """Test if .env file exists."""
    env_file = Path(__file__).parent / ".env"
    
    if env_file.exists():
        print("✅ .env file exists")
        
        # Check if API key is set
        with open(env_file, 'r', encoding='utf-8') as f:
            content = f.read()
            
        if "your_api_key_here" in content:
            print("⚠️  API key not configured (still placeholder)")
            return True
        else:
            print("✅ API key configured")
            return True
    else:
        print("❌ .env file not found")
        return False

def main():
    """Run all tests."""
    print("=" * 50)
    print("Spell Corrector Tests")
    print("=" * 50)
    print()
    
    tests = [
        ("Module Import", test_import),
        ("JSON Structure", test_json_structure),
        ("Environment File", test_env_file),
    ]
    
    results = []
    for name, test_func in tests:
        print(f"Testing: {name}")
        result = test_func()
        results.append(result)
        print()
    
    # Summary
    print("=" * 50)
    passed = sum(results)
    total = len(results)
    print(f"Results: {passed}/{total} tests passed")
    
    if passed == total:
        print("\n✅ All tests passed! Project is ready.")
        print("\nNext steps:")
        print("1. Configure your API key in .env")
        print("2. Install dependencies: pip install -r requirements.txt")
        print("3. Run: python corrector.py test_input.json test_output.json")
    else:
        print("\n❌ Some tests failed. Please fix the issues.")
    
    print("=" * 50)
    return passed == total

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
