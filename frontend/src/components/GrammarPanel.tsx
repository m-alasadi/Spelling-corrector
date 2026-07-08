import { useState, useCallback } from 'react';
import type { GrammarBatchResult } from '../types';
import { grammarCheck } from '../services/api';
import {
  Languages,
  Check,
  X,
  Loader2,
  AlertCircle,
} from 'lucide-react';

interface GrammarPanelProps {
  /** Currently selected text in the editor */
  selectedText: string;
  /** Callback when user wants to apply a grammar correction */
  onApplyCorrection: (original: string, corrected: string) => void;
  /** Callback to clear the grammar highlight */
  onClearHighlight: () => void;
  /** Whether grammar check is currently running */
  isChecking: boolean;
  /** All grammar results from batch check */
  grammarResults: GrammarBatchResult[];
  /** Count of grammar errors found */
  grammarErrorCount: number;
  /** Callback when user accepts a specific grammar error */
  onAcceptGrammarError: (segmentId: number) => void;
  /** Callback when user rejects a specific grammar error */
  onRejectGrammarError: (segmentId: number) => void;
  /** Set of segment IDs that have been accepted */
  acceptedErrors: Set<number>;
}

export default function GrammarPanel({
  selectedText,
  onApplyCorrection: _onApplyCorrection,
  onClearHighlight: _onClearHighlight,
  isChecking,
  grammarResults,
  grammarErrorCount: _grammarErrorCount,
  onAcceptGrammarError,
  onRejectGrammarError,
  acceptedErrors,
}: GrammarPanelProps) {
  const [singleCheckResult, setSingleCheckResult] = useState<{ original: string; corrected: string } | null>(null);
  const [singleChecking, setSingleChecking] = useState(false);
  const [singleError, setSingleError] = useState<string | null>(null);

  // Filter results that have actual changes
  const errors = grammarResults.filter((r) => r.original !== r.corrected);

  const handleSingleCheck = useCallback(async () => {
    if (!selectedText.trim()) return;
    setSingleChecking(true);
    setSingleError(null);
    setSingleCheckResult(null);
    try {
      const response = await grammarCheck(selectedText);
      if (response.original_text === response.corrected_text) {
        setSingleCheckResult(null);
      } else {
        setSingleCheckResult({ original: response.original_text, corrected: response.corrected_text });
      }
    } catch (err: any) {
      setSingleError(err.response?.data?.detail || 'حدث خطأ');
    } finally {
      setSingleChecking(false);
    }
  }, [selectedText]);

  return (
    <div className="h-full flex flex-col bg-white border-l border-gray-200">
      {/* Header */}
      <div className="px-4 py-3 border-b border-gray-200 bg-gradient-to-l from-blue-50 to-purple-50">
        <div className="flex items-center gap-2">
          <Languages className="w-5 h-5 text-blue-600" />
          <h3 className="text-sm font-semibold text-gray-800">التدقيق النحوي</h3>
        </div>
        <p className="text-xs text-gray-500 mt-1">
          حدد نصاً ثم اضغط "تدقيق نحوي" للكشف عن الأخطاء النحوية
        </p>
      </div>

      {/* Selected Text Preview */}
      {selectedText && (
        <div className="px-4 py-3 border-b border-gray-100 bg-gray-50">
          <div className="text-[10px] font-medium text-gray-400 mb-1 uppercase tracking-wider">
            النص المحدد
          </div>
          <p className="text-sm text-gray-700 leading-relaxed line-clamp-3" dir="rtl">
            {selectedText}
          </p>
        </div>
      )}

      {/* Check Button (for selected text) */}
      <div className="px-4 py-3 border-b border-gray-100">
        <button
          onClick={handleSingleCheck}
          disabled={!selectedText.trim() || singleChecking}
          className="w-full flex items-center justify-center gap-2 px-4 py-2.5 rounded-lg bg-gradient-to-r from-blue-500 to-purple-600 text-white text-sm font-semibold hover:from-blue-600 hover:to-purple-700 disabled:opacity-50 disabled:cursor-not-allowed transition-all shadow-sm"
        >
          {singleChecking ? (
            <>
              <Loader2 className="w-4 h-4 animate-spin" />
              جاري التدقيق النحوي...
            </>
          ) : (
            <>
              <Languages className="w-4 h-4" />
              تدقيق نحوي ✨
            </>
          )}
        </button>
      </div>

      {/* Results */}
      <div className="flex-1 overflow-y-auto px-4 py-3">
        {/* Loading State */}
        {isChecking && (
          <div className="flex flex-col items-center justify-center py-8 text-center">
            <div className="w-12 h-12 rounded-full bg-blue-50 flex items-center justify-center mb-3">
              <Loader2 className="w-6 h-6 text-blue-500 animate-spin" />
            </div>
            <p className="text-sm text-gray-600 font-medium">جاري التحليل النحوي...</p>
            <p className="text-xs text-gray-400 mt-1">يستخدم الذكاء الاصطناعي لفحص القواعد النحوية</p>
          </div>
        )}

        {/* Error State */}
        {singleError && (
          <div className="flex items-center gap-2 p-3 rounded-lg bg-red-50 border border-red-200 text-red-700 text-sm">
            <AlertCircle className="w-4 h-4 shrink-0" />
            <span>{singleError}</span>
          </div>
        )}

        {/* Empty state - show only before any check */}
        {!isChecking && !singleError && singleCheckResult === null && !selectedText && errors.length === 0 && grammarResults.length === 0 && (
          <div className="flex flex-col items-center justify-center py-12 text-center text-gray-400">
            <Languages className="w-10 h-10 mb-3 opacity-30" />
            <p className="text-sm">حدد نصاً في المحرر لبدء التدقيق النحوي</p>
          </div>
        )}

        {/* All Errors Found (auto batch check) */}
        {errors.length > 0 && (
          <div className="mb-4">
            <div className="text-[10px] font-medium text-gray-400 mb-2 uppercase tracking-wider">
              كل الأخطاء النحوية ({errors.length})
            </div>
            {errors.map((err) => {
              const isAccepted = acceptedErrors.has(err.id);
              return (
                <div
                  key={err.id}
                  className={`mb-2 p-2.5 rounded-lg border transition-all text-sm ${
                    isAccepted
                      ? 'bg-green-50 border-green-200 opacity-60'
                      : 'bg-blue-50 border-blue-200'
                  }`}
                >
                  <div className="mb-1" dir="rtl">
                    <span className={`font-medium ${isAccepted ? 'line-through text-gray-400' : 'text-red-700'}`}>
                      {err.original}
                    </span>
                  </div>
                  <div className="mb-2" dir="rtl">
                    <span className="text-green-700 font-medium">
                      {err.corrected}
                    </span>
                  </div>
                  {!isAccepted && (
                    <div className="flex items-center gap-2">
                      <button
                        onClick={() => onAcceptGrammarError(err.id)}
                        className="flex items-center gap-1 px-2.5 py-1 rounded text-xs font-medium text-white bg-green-600 hover:bg-green-700"
                      >
                        <Check className="w-3 h-3" /> قبول
                      </button>
                      <button
                        onClick={() => onRejectGrammarError(err.id)}
                        className="flex items-center gap-1 px-2.5 py-1 rounded text-xs font-medium text-gray-600 bg-gray-100 hover:bg-gray-200"
                      >
                        <X className="w-3 h-3" /> تجاهل
                      </button>
                    </div>
                  )}
                  {isAccepted && (
                    <div className="text-xs text-green-600 font-medium">✅ تم التصحيح</div>
                  )}
                </div>
              );
            })}
          </div>
        )}

        {/* No errors found after check */}
        {!isChecking && !singleError && errors.length === 0 && grammarResults.length > 0 && (
          <div className="flex flex-col items-center justify-center py-8 text-center">
            <div className="w-12 h-12 rounded-full bg-green-50 flex items-center justify-center mb-3">
              <Check className="w-6 h-6 text-green-500" />
            </div>
            <p className="text-sm text-gray-600 font-medium">✅ لا توجد أخطاء نحوية</p>
          </div>
        )}
      </div>

      {/* Stats Footer */}
      <div className="px-4 py-2 border-t border-gray-100 bg-gray-50 text-xs text-gray-400 flex items-center justify-between">
        <span>{errors.length} أخطاء نحوية</span>
        <span>{acceptedErrors.size} تم تصحيحها</span>
      </div>
    </div>
  );
}
