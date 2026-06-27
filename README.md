# 🔤 مدقق النصوص العربية — Arabic Spell Corrector

> نظام ذكي لتصحيح الأخطاء الإملائية في النصوص العربية، مصمم خصيصاً للنصوص المستخرجة من أنظمة التعرف على الصوت (ASR).

---

## 📋 ملخص المشروع

| البند | التفاصيل |
|-------|----------|
| **الغرض** | تصحيح الأخطاء الإملائية في النصوص العربية |
| **التقنيات** | Python, FastAPI, Flask, OpenAI API, Levenshtein |
| **اللغات المدعومة** | العربية (ar), الإنجليزية (en) |
| **صيغ الملفات** | JSON, TXT, SRT, VTT, PDF, DOCX |
| **Python** | 3.13+ |

---

## 🏗️ هيكل المشروع

```
Spelling-corrector/
│
├── 📄 README.md                    # هذا الملف
├── 📄 requirements.txt             # متطلبات Flask version
├── 📄 .env                         # مفتاح OpenAI API
├── 📄 .gitignore                   # ملفات التجاهل
│
├── 🐍 web_app.py                   # Flask backend (version 1)
├── 🐍 corrector.py                 # محرك التصحيح الأساسي (OpenAI)
├── 🐍 corrector_fast.py            # نسخة محسّنة للملفات الكبيرة
├── 🐍 file_converter.py            # تحويل صيغ الملفات المختلفة
├── 🐍 test_corrector.py            # اختبارات وحدات التحكم
│
├── 📁 templates/                   # قوالب Flask
│   ├── 📄 index.html               # صفحة الرفع الرئيسية
│   ├── 📄 editor.html              # محرر التصحيح التفاعلي (v1)
│   ├── 📄 results.html             # صفحة عرض النتائج
│   └── 📄 error.html               # صفحة الخطأ
│
├── 📁 backend/                     # FastAPI version (v2)
│   ├── 📄 requirements.txt         # متطلبات FastAPI
│   └── 📁 local_api/               # خادم FastAPI الرئيسي
│       ├── 🐍 main.py              # FastAPI app + Routes
│       ├── 🐍 spell_checker.py     # محرك التصحيح الهجين (Dict + AI)
│       ├── 🐍 dictionary.py        # مدير القاموس مع Levenshtein
│       ├── 📄 custom_dict.txt      # قاموس الأخطاء الإملائية الشائعة
│       ├── 📄 .env                 # مفتاح OpenAI API
│       ├── 📄 .gitignore           # ملفات التجاهل
│       └── 📁 templates/           # قوالب FastAPI
│           ├── 📄 index.html       # صفحة الرفع (v2)
│           └── 📄 editor.html      # محرر التصحيح (v2 - Microsoft-style)
│
├── 📁 uploads/                     # الملفات المرفوعة (مؤقتة)
├── 📁 exports/                     # الملفات المصححة (تصدير)
│
├── 📄 demo_input.json              # بيانات تجريبية (بدون أخطاء)
├── 📄 demo_output.json             # نتائج تجريبية
├── 📄 test_errors.json             # بيانات اختبار (بأخطاء)
├── 📄 test_input.json              # بيانات اختبار إضافية
├── 📄 test_output.json             # نتائج اختبار إضافية
├── 📄 realistic_asr_output.json    # مخرجات ASR واقعية
└── 📄 test_arabic.txt              # نص عربي للاختبار
```

---

## 🚀 التشغيل

### الطريقة الأولى: FastAPI (النسخة الرئيسية v2)

```bash
# 1. الانتقال لمجلد المشروع
cd Spelling-corrector/backend/local_api

# 2. تثبيت المتطلبات
pip install -r ../requirements.txt

# 3. إعداد مفتاح API
# عدّل ملف .env وأضف مفتاح OpenAI
echo OPENAI_API_KEY=sk-your-key-here > .env

# 4. تشغيل الخادم
python main.py
```

**الخادم يعمل على:** http://localhost:8000
**توثيق API:** http://localhost:8000/docs

### الطريقة الثانية: Flask (النسخة القديمة v1)

```bash
cd Spelling-corrector
pip install -r requirements.txt
echo OPENAI_API_KEY=sk-your-key-here > .env
python web_app.py
```

**الخادم يعمل على:** http://localhost:5000

---

## 🛠️ الأدوات والتقنيات

### Core Libraries

| المكتبة | الاستخدام | الإصدار |
|---------|----------|---------|
| `fastapi` | خادم API رئيسي (v2) | ≥0.104.0 |
| `uvicorn` | خادم ASGI لـ FastAPI | ≥0.24.0 |
| `flask` | خادم ويب (v1) | ≥3.0.0 |
| `openai` | التصحيح بالذكاء الاصطناعي | ≥1.0.0 |
| `python-Levenshtein` | اقتراح تصحيحات بالمسافة | ≥0.23.0 |
| `python-dotenv` | إدارة متغيرات البيئة | ≥1.0.0 |
| `python-multipart` | رفع الملفات | ≥0.0.6 |

### File Format Support

| الصيغة | المكتبة | الوصف |
|--------|---------|-------|
| `.json` | مدمج | مخرجات ASR |
| `.txt` | مدمج | النص العادي |
| `.srt` | مدمج | ملفات الترجمة |
| `.vtt` | مدمج | WebVTT |
| `.pdf` | `pdfplumber` | مستندات PDF |
| `.docx` | `python-docx` | مستندات Word |

---

## 📡 API Endpoints (FastAPI v2)

### الصفحات

| Method | Endpoint | الوصف |
|--------|----------|-------|
| `GET` | `/` | الصفحة الرئيسية (رفع الملف) |
| `GET` | `/editor/{job_id}` | محرر التصحيح التفاعلي |

### API Endpoints

| Method | Endpoint | الوصف | Request Body |
|--------|----------|-------|-------------|
| `POST` | `/upload` | رفع ملف | `file: UploadFile` |
| `POST` | `/correct/{job_id}` | تشغيل التصحيح | — |
| `POST` | `/api/apply` | تطبيق تصحيح كلمة واحدة | `{job_id, segment_index, word_index, action}` |
| `POST` | `/api/accept-all` | قبول جميع التصحيحات | `{job_id}` |
| `POST` | `/api/ignore-all` | تجاهل جميع التصحيحات | `{job_id}` |
| `GET` | `/api/download/{job_id}` | تحميل الملف المصحح | — |
| `GET` | `/api/stats/{job_id}` | إحصائيات التصحيح | — |
| `GET` | `/api/dictionary` | إحصائيات القاموس | — |
| `GET` | `/health` | فحص صحة الخادم | — |

---

## 🔧 المكونات الرئيسية

### 1. `spell_checker.py` — محرك التصحيح الهجين

```
النص → Tokenize → فحص القاموس المحلي → فحص AI (إذا لزم) → Word Diff → النتيجة
```

**الكلاسات والدوال الرئيسية:**
- `SpellChecker` — الكلاس الرئيسي
  - `correct_segment(text)` — تصحيح مقطع واحد
  - `correct_batch(texts)` — تصحيح مجموعة مقاطع
  - `get_stats()` — إحصائيات التصحيح
- `tokenize_arabic(text)` — تقسيم النص العربي لكلمات
- `compute_word_diff(original, corrected)` — مقارنة كلمة بكلمة
- `get_checker()` — الحصول على نسخة singleton

### 2. `dictionary.py` — مدير القاموس

**الكلاسات والدوال الرئيسية:**
- `DictionaryManager` — إدارة القاموس
  - `check_exact(word)` — بحث دقيق عن كلمة
  - `is_known_word(word)` — التحقق من وجود كلمة
  - `suggest_corrections(word)` — اقتراح تصحيحات بـ Levenshtein
  - `get_stats()` — إحصائيات القاموس
- `get_dictionary()` — الحصول على نسخة singleton

### 3. `custom_dict.txt` — القاموس المحلي

```
# Format: خطأ => صحيح
المشروووع => المشروع
الحيات <= الحياة  (كلمة صحيحة)
```

- **105+ كلمة صحيحة** مسجلة
- **14+ قاعدة أخطاء** شائعة
- يُدعم بـ Levenshtein للكلمات المشابهة

### 4. `main.py` — الخادم (FastAPI)

- إدارة المهام (`jobs` dict)
- معالجة الملفات المرفوعة
- حساب الفروقات على مستوى الكلمة
- واجهة برمجية للتفاعل مع المحرر

---

## 🎨 واجهة المحرر (editor.html)

### الميزات:

| الميزة | الوصف |
|--------|-------|
| **Ribbon Toolbar** | شريط أدوات يشبه Microsoft Office |
| **Status Bar** | شريط حالة مع اختصارات لوحة المفاتيح |
| **خطوط حمراء متعرجة** | `wavy underline` تحت الكلمات الخطأ |
| **قائمة منبثقة** | popup بالتصحيح المقترح عند النقر |
| **قبول/تجاهل** | لكل كلمة على حدة أو الكل معاً |
| **إعادة تعيين** | إعادة تجاهل الكلمات المتجاهلة |
| **تحميل النتيجة** | تحميل الملف المصحح |

### اختصارات لوحة المفاتيح:

| المفتاح | الوظيفة |
|---------|---------|
| `Tab` | الانتقال للخطأ التالي |
| `Shift+Tab` | الانتقال للخطأ السابق |
| `Enter` | قبول التصحيح |
| `Delete` / `Backspace` | تجاهل التصحيح |
| `Esc` | إغلاق القائمة المنبثقة |

---

## 📊 تدفق العمل

```
1️⃣  رفع الملف (JSON/TXT/SRT/VTT)
         ↓
2️⃣  معاينة المحتوى (عدد المقاطع، اللغة)
         ↓
3️⃣  ضغط "تصحيح النصوص"
         ↓
4️⃣  الخادم يعالج الملف:
    ├── فحص القاموس المحلي (سريع، مجاني)
    └── فحص AI (للمشكلات المعقدة)
         ↓
5️⃣  فتح المحرر التفاعلي:
    ├── خطوط حمراء تحت الأخطاء
    ├── نقر على كلمة → popup بالتصحيح
    ├── قبول أو تجاهل
    └── تحميل النتيجة النهائية
```

---

## 📁 هيكل البيانات

### صيغة الملفات المدعومة (JSON):

```json
{
  "job_id": "test-demo",
  "source_file": "demo.mp4",
  "language": "ar-SA",
  "segments": [
    {
      "id": 1,
      "start_ms": 0,
      "end_ms": 5000,
      "speaker": "المعلم",
      "text_original": "المشروووع في تقد dam جيد",
      "text_corrected": null
    }
  ]
}
```

### صيغة الكلمات بعد التصحيح:

```json
{
  "word_diffs": [
    {"type": "word", "value": "المشروووع", "is_error": true, "suggestion": "المشروع"},
    {"type": "space", "value": " ", "is_error": false},
    {"type": "word", "value": "في", "is_error": false, "suggestion": null},
    {"type": "word", "value": "تقد", "is_error": true, "suggestion": "تقدم"}
  ]
}
```

---

## 🧪 الاختبارات

```bash
# تشغيل اختبارات الوحدة
python test_corrector.py

# اختبار صيغة JSON
python -c "import json; print(json.load(open('test_input.json'))['segments'][:2])"
```

---

## 🔐 الإعداد

### متغيرات البيئة (.env):

```env
OPENAI_API_KEY=sk-your-key-here
```

### هيكل ملف .env:

```env
# OpenAI API Key for AI-powered corrections
# Get yours at: https://platform.openai.com/api-keys
OPENAI_API_KEY=
```

---

## 📝 ملاحظات تقنية

1. **الخوارزمية الهجينة**: تجمع بين القاموس المحلي (سريع، مجاني) والـ AI (ذكي، دقيق)
2. **Levenshtein Distance**: لاقتراح تصحيحات للكلمات المشابهة
3. **Word Diff**: مقارنة كلمة بكلمة لتحديد الأخطاء بدقة
4. **merged words**: عند استبدال عدة كلمات بكلمة واحدة، تُخفى الكلمات الزائدة
5. **FastAPI vs Flask**: النسخة الجديدة (FastAPI) أسرع بـ 2-3x من Flask

---

## 📞 الدعم

- **المطور**: m-alasadi
- **المستودع**: [Spelling-corrector](https://github.com/m-alasadi/Spelling-corrector)

---

## 📄 الترخيص

هذا المشروع مفتوح المصدر.
