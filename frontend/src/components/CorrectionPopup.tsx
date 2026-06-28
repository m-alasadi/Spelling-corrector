import { useEffect, useRef } from 'react';
import { Check, X, ArrowLeft, BookOpen } from 'lucide-react';

interface CorrectionPopupProps {
  original: string;
  suggestion: string;
  position: { top: number; left: number };
  onAccept: () => void;
  onIgnore: () => void;
  onAddToDict?: () => void;
  onClose: () => void;
}

export default function CorrectionPopup({
  original,
  suggestion,
  position,
  onAccept,
  onIgnore,
  onAddToDict,
  onClose,
}: CorrectionPopupProps) {
  const popupRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    function handleClickOutside(e: MouseEvent) {
      if (popupRef.current && !popupRef.current.contains(e.target as Node)) {
        onClose();
      }
    }
    function handleEscape(e: KeyboardEvent) {
      if (e.key === 'Escape') onClose();
      if (e.key === 'Enter') onAccept();
      if (e.key === 'Delete') onIgnore();
    }

    document.addEventListener('mousedown', handleClickOutside);
    document.addEventListener('keydown', handleEscape);
    return () => {
      document.removeEventListener('mousedown', handleClickOutside);
      document.removeEventListener('keydown', handleEscape);
    };
  }, [onClose, onAccept, onIgnore]);

  return (
    <div
      ref={popupRef}
      className="fixed z-[1000] animate-in fade-in slide-in-from-bottom-2 duration-150"
      style={{ top: position.top, left: position.left }}
    >
      <div className="bg-white rounded-xl shadow-2xl border border-gray-200 w-[320px] overflow-hidden">
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
              <div className="text-lg font-bold text-red-500 line-through decoration-red-300 opacity-70 font-arabic">
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
              <div className="text-xl font-bold text-blue-600 font-arabic">
                {suggestion || '—'}
              </div>
            </div>
          </div>
        </div>

        {/* Actions */}
        <div className="flex gap-2 px-4 pb-4">
          <button
            onClick={onAccept}
            className="flex-1 flex items-center justify-center gap-2 px-4 py-2.5 rounded-lg bg-gradient-to-r from-green-500 to-emerald-600 text-white text-sm font-semibold hover:from-green-600 hover:to-emerald-700 transition-all shadow-sm"
          >
            <Check className="w-4 h-4" />
            قبول التصحيح
          </button>
          <button
            onClick={onIgnore}
            className="flex items-center justify-center gap-2 px-3 py-2.5 rounded-lg bg-gray-100 text-gray-600 text-sm font-semibold hover:bg-gray-200 border border-gray-200 transition-all"
          >
            <X className="w-4 h-4" />
            تجاهل
          </button>
          {onAddToDict && (
            <button
              onClick={onAddToDict}
              className="flex items-center justify-center gap-2 px-3 py-2.5 rounded-lg bg-blue-50 text-blue-600 text-sm font-semibold hover:bg-blue-100 border border-blue-200 transition-all"
              title="حفظ الكلمة في القاموس"
            >
              <BookOpen className="w-4 h-4" />
            </button>
          )}
        </div>
      </div>
    </div>
  );
}
