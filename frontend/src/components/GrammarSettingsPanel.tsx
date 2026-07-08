import { useCallback } from 'react';
import { useTextContext } from '../context/TextContext';
import { Loader2, Rocket, Settings2, Languages, Type } from 'lucide-react';
import { clsx } from 'clsx';
import * as api from '../services/api';

export default function GrammarSettingsPanel() {
  const {
    cleanText,
    grammarOptions,
    setGrammarOptions,
    setGrammarErrors,
    isGrammarProcessing,
    setIsGrammarProcessing,
  } = useTextContext();

  const handleProcess = useCallback(async () => {
    if (!cleanText.trim() || isGrammarProcessing) return;

    setIsGrammarProcessing(true);

    try {
      // Build segments from clean text (split by paragraphs)
      const paragraphs = cleanText.split('\n').filter((p: string) => p.trim());
      const segments = paragraphs.map((text: string, idx: number) => ({
        id: idx + 1,
        text: text.trim(),
      }));

      // Use stage2 endpoint with options
      const mode = grammarOptions.processingLevel === 'full-fusha' ? 'msa' : 'preserve';
      const result = await api.stage2GrammarStyleBatch(
        segments,
        grammarOptions.addPunctuation,
        mode
      );

      // Convert results to GrammarErrorData
      const errors = result.results
        .filter((r) => r.original !== r.corrected)
        .map((r) => ({
          id: `grammar-${r.id}`,
          original: r.original,
          suggestion: r.corrected,
          errorType: grammarOptions.addPunctuation ? 'punctuation' as const : 'grammar' as const,
          accepted: false,
          rejected: false,
        }));

      setGrammarErrors(errors);
    } catch (err) {
      console.error('Grammar check failed:', err);
    } finally {
      setIsGrammarProcessing(false);
    }
  }, [cleanText, grammarOptions, isGrammarProcessing, setIsGrammarProcessing, setGrammarErrors]);

  return (
    <div className="w-72 bg-white border-l border-gray-200 overflow-y-auto shadow-inner">
      {/* Header */}
      <div className="px-4 py-4 bg-gradient-to-b from-indigo-50 to-white border-b border-gray-100">
        <div className="flex items-center gap-2 mb-1">
          <Settings2 className="w-4 h-4 text-indigo-500" />
          <h3 className="text-sm font-bold text-gray-800">إعدادات المعالجة</h3>
        </div>
        <p className="text-xs text-gray-400">خصّص طريقة التدقيق النحوي</p>
      </div>

      {/* Settings */}
      <div className="p-4 space-y-5">
        {/* Toggle: Add Punctuation */}
        <div className="space-y-2">
          <div
            onClick={() =>
              setGrammarOptions({
                ...grammarOptions,
                addPunctuation: !grammarOptions.addPunctuation,
              })
            }
            className={clsx(
              'flex items-center justify-between p-3 rounded-xl cursor-pointer transition-all duration-200 border-2',
              grammarOptions.addPunctuation
                ? 'bg-emerald-50 border-emerald-400 shadow-sm shadow-emerald-100'
                : 'bg-gray-50 border-gray-200 hover:border-gray-300'
            )}
          >
            <div className="flex items-center gap-2.5">
              <div className={clsx(
                'w-8 h-8 rounded-lg flex items-center justify-center transition-colors',
                grammarOptions.addPunctuation
                  ? 'bg-emerald-100 text-emerald-600'
                  : 'bg-gray-100 text-gray-400'
              )}>
                <Type className="w-4 h-4" />
              </div>
              <div>
                <span className={clsx(
                  'text-sm font-semibold block',
                  grammarOptions.addPunctuation ? 'text-emerald-700' : 'text-gray-700'
                )}>
                  إضافة علامات الترقيم
                </span>
                <span className="text-[10px] text-gray-400">
                  نقاط وفواصل في مواضع التوقف
                </span>
              </div>
            </div>
            <div
              className={clsx(
                'relative w-11 h-6 rounded-full transition-all duration-200',
                grammarOptions.addPunctuation
                  ? 'bg-emerald-500 shadow-inner'
                  : 'bg-gray-300'
              )}
            >
              <div
                className={clsx(
                  'absolute top-0.5 w-5 h-5 bg-white rounded-full shadow-md transition-all duration-200',
                  grammarOptions.addPunctuation
                    ? 'translate-x-0.5'
                    : 'translate-x-[22px]'
                )}
              />
            </div>
          </div>
        </div>

        {/* Dropdown: Processing Level */}
        <div className="space-y-2">
          <div className="flex items-center gap-2.5 mb-1">
            <div className="w-8 h-8 rounded-lg flex items-center justify-center bg-indigo-50 text-indigo-500">
              <Languages className="w-4 h-4" />
            </div>
            <span className="text-sm font-semibold text-gray-700">مستوى المعالجة</span>
          </div>
          <select
            value={grammarOptions.processingLevel}
            onChange={(e) =>
              setGrammarOptions({
                ...grammarOptions,
                processingLevel: e.target.value as 'grammar-only' | 'full-fusha',
              })
            }
            className="w-full px-3 py-2.5 bg-gray-50 border-2 border-gray-200 rounded-xl text-sm text-gray-700 focus:outline-none focus:border-indigo-400 focus:ring-2 focus:ring-indigo-100 transition-all cursor-pointer hover:border-gray-300"
          >
            <option value="grammar-only">
              تدقيق نحوي فقط (الحفاظ على العامية)
            </option>
            <option value="full-fusha">
              تحويل كامل إلى الفصحى (رسمي)
            </option>
          </select>
          <p className={clsx(
            'text-xs pr-1 transition-colors',
            grammarOptions.processingLevel === 'full-fusha' ? 'text-indigo-500 font-medium' : 'text-gray-400'
          )}>
            {grammarOptions.processingLevel === 'grammar-only'
              ? 'سيتم تصحيح القواعد النحوية فقط مع الحفاظ على الكلمات العامية'
              : 'سيتم تحويل النص بالكامل إلى اللغة العربية الفصحى'}
          </p>
        </div>

        {/* Process Button */}
        <div className="pt-2">
          <button
            onClick={handleProcess}
            disabled={!cleanText.trim() || isGrammarProcessing}
            className={clsx(
              'w-full flex items-center justify-center gap-2 px-4 py-3 rounded-xl text-sm font-bold transition-all duration-200',
              cleanText.trim() && !isGrammarProcessing
                ? 'bg-gradient-to-r from-indigo-500 to-purple-600 text-white shadow-lg shadow-indigo-200 hover:shadow-indigo-300 hover:from-indigo-600 hover:to-purple-700'
                : 'bg-gray-100 text-gray-400 cursor-not-allowed'
            )}
          >
            {isGrammarProcessing ? (
              <>
                <Loader2 className="w-4 h-4 animate-spin" />
                جاري المعالجة...
              </>
            ) : (
              <>
                <Rocket className="w-4 h-4" />
                🚀 تشغيل المعالجة المتقدمة
              </>
            )}
          </button>
        </div>
      </div>

      {/* Info Section */}
      <div className="px-4 py-3 bg-gray-50 border-t border-gray-100">
        <div className="flex items-start gap-2">
          <div className="w-5 h-5 rounded-full bg-blue-100 flex items-center justify-center mt-0.5 shrink-0">
            <span className="text-xs text-blue-600 font-bold">؟</span>
          </div>
          <div>
            <p className="text-xs text-gray-500 leading-relaxed">
              بعد الضغط على زر المعالجة، ستظهر التعديلات النحوية في المحرر بخط أزرق مزدوج.
              اضغط على أي كلمة زرقاء لعرض الاقتراح.
            </p>
          </div>
        </div>
      </div>
    </div>
  );
}
