# Arabic Spell Corrector

تصحيح إملائي للنصوص العربية الناتجة من أنظمة تحويل الصوت إلى نص (ASR)

## الهدف

هذه المرحلة مسؤولة عن **التدقيق الإملائي فقط** للنصوص العربية، مع الحفاظ على المعنى الأصلي وال اللهجة.

## المتطلبات

- Python 3.8+
- مفتاح OpenAI API

## التثبيت

```bash
# الانتقال إلى مجلد المشروع
cd backend/spell_corrector

# إنشاء بيئة افتراضية
python -m venv venv

# تفعيل البيئة (Windows)
venv\Scripts\activate

# تفعيل البيئة (Linux/Mac)
source venv/bin/activate

# تثبيت المتطلبات
pip install -r requirements.txt

# إعداد مفتاح API
# قم بتعديل ملف .env وأضف مفتاح OpenAI الخاص بك
```

## الاستخدام

### كسطر أوامر

```bash
python corrector.py input.json output.json
```

### كمكتبة Python

```python
from corrector import SpellCorrector

# تهيئة المصحح
corrector = SpellCorrector(api_key="your_api_key")

# تصحيح نص واحد
corrected = corrector.correct_text("هاذا نص تجريبي")
print(corrected)  # هذا نص تجريبي

# معالجة ملف JSON
stats = corrector.process_json("asr_output.json", "corrected_output.json")
```

## صيغة الإدخال

```json
{
  "job_id": "uuid",
  "source_file": "lecture.mp4",
  "language": "ar-SA",
  "engine": "x-seedasr-2.0",
  "duration_ms": 7200000,
  "segments": [
    {
      "id": 1,
      "start_ms": 1000,
      "end_ms": 5200,
      "speaker": null,
      "text_original": "هاذا نص تجريبي",
      "text_corrected": null
    }
  ]
}
```

## صيغة الإخراج

```json
{
  "job_id": "uuid",
  "source_file": "lecture.mp4",
  "language": "ar-SA",
  "engine": "x-seedasr-2.0",
  "duration_ms": 7200000,
  "segments": [
    {
      "id": 1,
      "start_ms": 1000,
      "end_ms": 5200,
      "speaker": null,
      "text_original": "هاذا نص تجريبي",
      "text_corrected": "هذا نص تجريبي"
    }
  ]
}
```

## قواعد التصحيح

1. تصحيح إملائي فقط
2. عدم إعادة صياغة الجملة
3. عدم تغيير المعنى
4. عدم حذف أي جملة
5. عدم اختصار الكلام
6. عدم إضافة شرح أو كلمات جديدة
7. عدم دمج مقطعين معًا
8. عدم تغيير ترتيب المقاطع
9. الحفاظ على أسماء الأشخاص قدر الإمكان
10. إذا لم تكن الكلمة واضحة، تترك كما هي
11. لا يتم تعديل اللهجة إلا إذا كان الخطأ إملائيًا واضحًا
12. لا يتم تحويل النص إلى لغة فصحى إذا كان الأصلي باللهجة

## المميزات

- ✅ تصحيح إملائي دقيق للنصوص العربية
- ✅ حفظ اللهجة الأصلية
- ✅ نظام تخزين مؤقت لتوفير التكلفة
- ✅ معالجة سريعة للنصوص الطويلة
- ✅ سجل أخطاء مفصل
- ✅ مستقل تماماً عن باقي النظام

## التكاليف

- يستخدم OpenAI API (مدفوع)
- التكلفة تعتمد على:
  - عدد المقاطع النصية
  - طول كل مقطع
  - النموذج المختار (GPT-4 أغلى من GPT-3.5)

## ملاحظات

- هذه المرحلة مستقلة تماماً
- المدخل: `input.json`
- المخرج: `output.json`
- لا تحتاج إلى معرفة تفاصيل النظام الآخر

## الترخيص

مشروع خاص
