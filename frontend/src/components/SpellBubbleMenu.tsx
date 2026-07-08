import { useCallback, useState, useEffect, useRef } from 'react';
import type { Editor } from '@tiptap/react';
import { Check, X, Pencil, Languages } from 'lucide-react';
import { useTextContext } from '../context/TextContext';

interface SpellBubbleMenuProps {
  editor: Editor;
}

interface StoredMark {
  from: number;
  to: number;
  suggestion: string;
  wordIndex: number;
  segmentId: number;
}

export default function SpellBubbleMenu({ editor }: SpellBubbleMenuProps) {
  const { acceptSpellError, ignoreSpellError } = useTextContext();
  const [manualMode, setManualMode] = useState(false);
  const [manualValue, setManualValue] = useState('');
  const [visible, setVisible] = useState(false);
  const [position, setPosition] = useState({ top: 0, left: 0 });
  const menuRef = useRef<HTMLDivElement>(null);
  const storedMarkRef = useRef<StoredMark | null>(null);

  // ── Find spell error mark range at current cursor ──
  const findMarkRange = useCallback((): StoredMark | null => {
    const { from } = editor.state.selection;
    const state = editor.state;
    const $pos = state.doc.resolve(from);
    const marks = $pos.marks();
    const spellMark = marks.find((m) => m.type.name === 'spellError');
    if (!spellMark) return null;

    // Use ProseMirror's node-based mark detection
    // Find the text node that contains the cursor
    const parentNode = $pos.parent;
    const parentStart = $pos.before();
    
    // Get the suggestion from the mark attrs
    const suggestion = (spellMark.attrs.suggestion as string) || '';
    const wordIndex = (spellMark.attrs.wordIndex as number) || 0;
    const segmentId = (spellMark.attrs.segmentId as number) || 0;
    
    // Walk through parent node's inline children to find the marked text
    let markStart = -1;
    let markEnd = -1;
    
    parentNode.forEach((child, offset) => {
      if (child.isText && child.marks.some(m => m.type.name === 'spellError')) {
        const nodeStart = parentStart + 1 + offset;
        const nodeEnd = nodeStart + child.nodeSize;
        if (from >= nodeStart && from <= nodeEnd) {
          markStart = nodeStart;
          markEnd = nodeEnd;
        }
      }
    });
    
    if (markStart === -1) return null;
    
    return {
      from: markStart,
      to: markEnd,
      suggestion,
      wordIndex,
      segmentId,
    };
  }, [editor]);

  // ── Track selection and show/hide menu ──
  useEffect(() => {
    const updatePosition = () => {
      if (!editor.isActive('spellError')) {
        setVisible(false);
        storedMarkRef.current = null;
        return;
      }

      const markRange = findMarkRange();
      if (!markRange) {
        setVisible(false);
        return;
      }

      // Store the mark range for later use
      storedMarkRef.current = markRange;

      const { view } = editor;
      const { from } = editor.state.selection;
      const coords = view.coordsAtPos(from);

      setPosition({
        top: coords.top - 10,
        left: coords.left,
      });
      setVisible(true);
    };

    editor.on('selectionUpdate', updatePosition);
    editor.on('focus', updatePosition);

    const editorEl = editor.view.dom;
    const handleClick = () => setTimeout(updatePosition, 10);
    editorEl.addEventListener('click', handleClick);

    return () => {
      editor.off('selectionUpdate', updatePosition);
      editor.off('focus', updatePosition);
      editorEl.removeEventListener('click', handleClick);
    };
  }, [editor, findMarkRange]);

  // ── Click outside to close ──
  useEffect(() => {
    const handleClick = (e: MouseEvent) => {
      if (menuRef.current && !menuRef.current.contains(e.target as Node)) {
        setVisible(false);
        storedMarkRef.current = null;
      }
    };
    document.addEventListener('mousedown', handleClick);
    return () => document.removeEventListener('mousedown', handleClick);
  }, []);

  // ── Accept correction ──
  const handleAccept = useCallback(() => {
    const mark = storedMarkRef.current;
    if (!mark || !mark.suggestion) return;

    const { from, to, suggestion } = mark;
    
    // Get the text before and after the mark range to verify
    const state = editor.state;
    const textBefore = from > 0 ? state.doc.textBetween(Math.max(0, from - 1), from) : '';
    const textAfter = to < state.doc.content.size ? state.doc.textBetween(to, Math.min(state.doc.content.size, to + 1)) : '';
    
    console.log('Replacing:', { from, to, suggestion, textBefore, textAfter });
    
    // Use a transaction to replace the text atomically
    const tr = state.tr;
    tr.delete(from, to);
    tr.insert(from, state.schema.text(suggestion));
    editor.view.dispatch(tr);

    const id = `spell-${mark.segmentId}-${mark.wordIndex}`;
    acceptSpellError(id);
    setVisible(false);
    storedMarkRef.current = null;
  }, [editor, acceptSpellError]);

  // ── Ignore correction ──
  const handleIgnore = useCallback(() => {
    const mark = storedMarkRef.current;
    if (!mark) return;

    // Remove the spell error mark from the range
    const { from, to } = mark;
    const state = editor.state;
    const markType = state.schema.marks.spellError;
    const tr = state.tr.removeMark(from, to, markType);
    editor.view.dispatch(tr);

    const id = `spell-${mark.segmentId}-${mark.wordIndex}`;
    ignoreSpellError(id);
    setVisible(false);
    storedMarkRef.current = null;
  }, [editor, ignoreSpellError]);

  // ── Manual correction ──
  const handleManualCorrect = useCallback(() => {
    const val = manualValue.trim();
    const mark = storedMarkRef.current;
    if (!val || !mark) return;

    const { from, to } = mark;
    const state = editor.state;
    const tr = state.tr;
    tr.delete(from, to);
    tr.insert(from, state.schema.text(val));
    editor.view.dispatch(tr);

    const id = `spell-${mark.segmentId}-${mark.wordIndex}`;
    acceptSpellError(id);
    setManualMode(false);
    setManualValue('');
    setVisible(false);
    storedMarkRef.current = null;
  }, [editor, manualValue, acceptSpellError]);

  if (!visible) return null;

  const suggestion = storedMarkRef.current?.suggestion || '';

  return (
    <div
      ref={menuRef}
      className="fixed z-[1000] animate-in fade-in slide-in-from-bottom-2"
      style={{
        top: position.top,
        left: position.left,
        transform: 'translate(-50%, -100%)',
      }}
    >
      <div className="bg-white rounded-xl shadow-2xl border border-gray-200 w-[320px] overflow-hidden">
        {/* Header */}
        <div className="flex items-center justify-between px-3.5 py-2 bg-red-50 border-b border-red-100">
          <div className="flex items-center gap-1.5">
            <Languages className="w-3.5 h-3.5 text-red-500" />
            <span className="text-xs font-semibold text-red-700">
              📝 اقتراح إملائي
            </span>
          </div>
          <button
            onClick={() => {
              setVisible(false);
              storedMarkRef.current = null;
            }}
            className="w-5 h-5 rounded flex items-center justify-center text-gray-400 hover:bg-red-100 hover:text-red-600 transition-colors"
          >
            <X className="w-3 h-3" />
          </button>
        </div>

        {/* Suggestion */}
        {!manualMode && (
          <div className="px-3.5 py-3">
            <div className="text-center mb-3">
              <span className="text-xs text-gray-400 uppercase tracking-wider">
                الكلمة المقترحة
              </span>
              <div
                className="text-xl font-bold text-blue-600 mt-1"
                style={{ fontFamily: "'Noto Naskh Arabic', serif" }}
              >
                {suggestion || '—'}
              </div>
            </div>

            {/* Action Buttons */}
            <div className="flex gap-2">
              <button
                onMouseDown={(e) => {
                  e.preventDefault();
                  handleAccept();
                }}
                className="flex-1 flex items-center justify-center gap-1.5 px-3 py-2 rounded-lg bg-gradient-to-r from-green-500 to-emerald-600 text-white text-xs font-semibold hover:from-green-600 hover:to-emerald-700 transition-all shadow-sm"
              >
                <Check className="w-3.5 h-3.5" />
                قبول
              </button>
              <button
                onMouseDown={(e) => {
                  e.preventDefault();
                  handleIgnore();
                }}
                className="flex-1 flex items-center justify-center gap-1.5 px-3 py-2 rounded-lg bg-gray-100 text-gray-600 text-xs font-semibold hover:bg-gray-200 transition-all"
              >
                <X className="w-3.5 h-3.5" />
                تجاهل
              </button>
              <button
                onMouseDown={(e) => {
                  e.preventDefault();
                  setManualMode(true);
                  setManualValue(suggestion || '');
                }}
                className="flex items-center justify-center px-2.5 py-2 rounded-lg bg-amber-50 text-amber-600 hover:bg-amber-100 transition-all"
              >
                <Pencil className="w-3.5 h-3.5" />
              </button>
            </div>
          </div>
        )}

        {/* Manual Correction */}
        {manualMode && (
          <div className="px-3.5 py-3">
            <div className="flex items-center gap-2">
              <input
                type="text"
                value={manualValue}
                onChange={(e) => setManualValue(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter') handleManualCorrect();
                  if (e.key === 'Escape') {
                    setManualMode(false);
                    setManualValue('');
                  }
                }}
                placeholder="اكتب التصحيح اليدوي..."
                className="flex-1 px-3 py-2 border border-gray-200 rounded-lg text-sm focus:outline-none focus:border-blue-400 focus:ring-2 focus:ring-blue-100"
                style={{ fontFamily: "'Noto Naskh Arabic', serif" }}
                autoFocus
              />
            </div>
            <div className="flex gap-2 mt-2">
              <button
                onClick={handleManualCorrect}
                disabled={!manualValue.trim()}
                className="flex-1 px-3 py-1.5 bg-blue-500 text-white rounded-lg text-xs font-semibold hover:bg-blue-600 disabled:opacity-40 transition-all"
              >
                حفظ
              </button>
              <button
                onClick={() => {
                  setManualMode(false);
                  setManualValue('');
                }}
                className="px-3 py-1.5 bg-gray-100 text-gray-600 rounded-lg text-xs hover:bg-gray-200 transition-all"
              >
                إلغاء
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
