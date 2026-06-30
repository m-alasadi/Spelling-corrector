import { useEffect, useRef, useState } from 'react';
import { Check, X, ArrowLeft, BookOpen, Pencil } from 'lucide-react';

interface CorrectionPopupProps {
  original: string;
  suggestion: string;
  position: { top: number; left: number };
  onAccept: () => void;
  onIgnore: () => void;
  onManualCorrect: (corrected: string) => void;
  onClose: () => void;
}

export default function CorrectionPopup({
  original,
  suggestion,
  position,
  onAccept,
  onIgnore,
  onManualCorrect,
  onClose,
}: CorrectionPopupProps) {
  const popupRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  const [manualMode, setManualMode] = useState(false);
  const [manualValue, setManualValue] = useState('');

  useEffect(() => {
    function handleClickOutside(e: MouseEvent) {
      if (popupRef.current && !popupRef.current.contains(e.target as Node)) {
        onClose();
      }
    }
    function handleEscape(e: KeyboardEvent) {
      if (e.key === 'Escape') onClose();
      if (e.key === 'Enter' && !manualMode) onAccept();
      if (e.key === 'Delete' && !manualMode) onIgnore();
    }

    document.addEventListener('mousedown', handleClickOutside);
    document.addEventListener('keydown', handleEscape);
    return () => {
      document.removeEventListener('mousedown', handleClickOutside);
      document.removeEventListener('keydown', handleEscape);
    };
  }, [onClose, onAccept, onIgnore, manualMode]);

  // Focus input when manual mode activates
  useEffect(() => {
    if (manualMode && inputRef.current) {
      inputRef.current.focus();
      inputRef.current.select();
    }
  }, [manualMode]);

  const handleManualSubmit = () => {
    const val = manualValue.trim();
    if (val && val !== original) {
      onManualCorrect(val);
      setManualMode(false);
      setManualValue('');
    }
  };

  return (
    <div
      ref={popupRef}
      className="fixed z-[1000] animate-in fade-in slide-in-from-bottom-2 duration-150"
      style={{ top: position.top, left: position.left }}
    >
      <div className="bg-white rounded-xl shadow-2xl border border-gray-200 w-[340px] overflow-hidden">
        {/* Header */}
        <div className="flex items-center justify-between px-4 py-2.5 bg-gray-50 border-b border-gray-100">
          <span className="text-xs font-semibold text-gray-500 uppercase tracking-wider">
            💡 تصحيح مقترح
          </span>
          <button
            onClick={onClose}
            className="w-5 h-5 rounded flex items-center justify-center text-gray-400 hover:bg-gray-200 hover:text-gray-600 transition-colors"
          >
            <X className="w-3.5 h-3.5" />
          </button>
        </div>

        {/* Comparison */}
        <div className="px-4 py-4">
          <div className="grid grid-cols-[1fr_auto_1fr] gap-3 items-center">
            {/* Original */}
            <div className="text-center">
              <div className="text-[10px] text-gray-400 uppercase tracking-wider mb-1.5 font-medium">
                الأصلي
              </div>
              <div className="text-lg font-bold text-red-500 line-through decoration-red-300 opacity-70" style={{ fontFamily: "'Noto Naskh Arabic', serif" }}>
                {original}
              </div>
            </div>

            {/* Arrow */}
            <ArrowLeft className="w-5 h-5 text-gray-300" />

            {/* Suggestion */}
            <div className="text-center">
              <div className="text-[10px] text-gray-400 uppercase tracking-wider mb-1.5 font-medium">
                التصحيح
              </div>
              <div className="text-xl font-bold text-blue-600" style={{ fontFamily: "'Noto Naskh Arabic', serif" }}>
                {suggestion || '—'}
              </div>
            </div>
          </div>
        </div>

        {/* Manual Correction Input */}
        {manualMode && (
          <div className="px-4 pb-3">
            <div className="flex items-center gap-2">
              <Pencil className="w-4 h-4 text-gray-400 shrink-0" />
              <input
                ref={inputRef}
                type="text"
                value={manualValue}
                onChange={(e) => setManualValue(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter') handleManualSubmit();
                  if (e.key === 'Escape') { setManualMode(false); setManualValue(''); }
                }}
                placeholder="اكتب التصحيح اليدوي..."
                className="flex-1 px-3 py-2 border border-gray-200 rounded-lg text-sm focus:outline-none focus:border-blue-400 focus:ring-2 focus:ring-blue-100"
                style={{ fontFamily: "'Noto Naskh Arabic', serif" }}
              />
              <button
                onClick={handleManualSubmit}
                disabled={!manualValue.trim() || manualValue.trim() === original}
                className="px-3 py-2 bg-blue-500 text-white rounded-lg text-sm font-semibold hover:bg-blue-600 disabled:opacity-40 disabled:cursor-not-allowed transition-all"
              >
                حفظ
              </button>
            </div>
            <p className="text-[10px] text-gray-400 mt-1">
              سيتم حفظ التصحيح في القاموس للاستخدام المستقبلي
            </p>
          </div>
        )}

        {/* Actions */}
        <div className="flex gap-2 px-4 pb-4">
          <button
            onClick={onAccept}
            className="flex-1 flex items-center justify-center gap-2 px-4 py-2.5 rounded-lg bg-gradient-to-r from-green-500 to-emerald-600 text-white text-sm font-semibold hover:from-green-600 hover:to-emerald-700 transition-all shadow-sm"
          >
            <Check className="w-4 h-4" />
            قبول
          </button>
          <button
            onClick={onIgnore}
            className="flex items-center justify-center gap-2 px-3 py-2.5 rounded-lg bg-gray-100 text-gray-600 text-sm font-semibold hover:bg-gray-200 border border-gray-200 transition-all"
          >
            <X className="w-4 h-4" />
            تجاهل
          </button>
          <button
            onClick={() => { setManualMode(!manualMode); setManualValue(suggestion || ''); }}
            className="flex items-center justify-center gap-2 px-3 py-2.5 rounded-lg bg-blue-50 text-blue-600 text-sm font-semibold hover:bg-blue-100 border border-blue-200 transition-all"
            title="تصحيح يدوي + حفظ في القاموس"
          >
            <Pencil className="w-4 h-4" />
          </button>
        </div>
      </div>
    </div>
  );
}
