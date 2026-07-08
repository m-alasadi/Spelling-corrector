import httpx
import json

print("=" * 60)
print("اختبار: هل المشروع يعدل على اللهجة العامية؟")
print("=" * 60)

# Test 1: Grammar check
print("\n--- التدقيق النحوي ---")
r1 = httpx.post('http://localhost:8000/api/grammar-check-batch', json={'segments': [
    {'id': 1, 'text': 'نحن عندنا مشاكل لازم نحلها هسه'},
    {'id': 2, 'text': 'هذا المktab كبير وشلون حالك'},
    {'id': 3, 'text': 'شنو رأيك بالموضوع'},
]})
for r in r1.json()['results']:
    same = "✅ SAME" if r['original'] == r['corrected'] else "❌ CHANGED"
    print(f"  [{r['id']}] {r['original']}")
    print(f"         => {r['corrected']}")
    print(f"         {same}")

# Test 2: Spell check (single word)
print("\n--- التصحيح الإملائي (كلمة واحدة) ---")
r2 = httpx.post('http://localhost:8000/api/grammar-check-batch', json={'segments': [
    {'id': 1, 'text': 'هسه'},
    {'id': 2, 'text': 'شلون'},
    {'id': 3, 'text': 'عندنا'},
    {'id': 4, 'text': 'شنو'},
]})
for r in r2.json()['results']:
    same = "✅ SAME" if r['original'] == r['corrected'] else "❌ CHANGED"
    print(f"  [{r['id']}] '{r['original']}' => '{r['corrected']}' {same}")
