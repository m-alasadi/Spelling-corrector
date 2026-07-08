import { useCallback, useEffect, useRef, useState } from 'react';
import type { Editor } from '@tiptap/react';
import { Check, X, Ruler } from 'lucide-react';
import { useTextContext } from '../context/TextContext';

interface GrammarBubbleMenuProps {
  editor: Editor;
}

interface StoredMark {
  from: number;
  to: number;
  suggestion: string;
  errorType: string;
}

export default function GrammarBubbleMenu({ editor }: GrammarBubbleMenuProps) {
  const { acceptGrammarError, rejectGrammarError } = useTextContext();
  const [visible, setVisible] = useState(false);
  const [position, setPosition] = useState({ top: 0, left: 0 });
  const menuRef = useRef<HTMLDivElement>(null);
  const storedMarkRef = useRef<StoredMark | null>(null);

  // ── Find grammar error mark range at current cursor ──
  const findMarkRange = useCallback((): StoredMark | null => {
    const { from } = editor.state.selection;
    const state = editor.state;
    const $pos = state.doc.resolve(from);
    const marks = $pos.marks();
    const grammarMark = marks.find((m) => m.type.name === 'grammarError');
    if (!grammarMark) return null;

    const parentNode = $pos.parent;
    const parentStart = $pos.before();

    let markStart = -1;
    let markEnd = -1;

    parentNode.forEach((child, offset) => {
      if (child.isText && child.marks.some(m => m.type.name === 'grammarError')) {
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
      suggestion: (grammarMark.attrs.suggestion as string) || '',
      errorType: (grammarMark.attrs.errorType as string) || 'grammar',
    };
  }, [editor]);

  // ── Track selection and show/hide menu ──
  useEffect(() => {
    const updatePosition = () => {
      if (!editor.isActive('grammarError')) {
        setVisible(false);
        storedMarkRef.current = null;
        return;
      }

      const markRange = findMarkRange();
      if (!markRange) {
        setVisible(false);
        return;
      }

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

  // ── Accept grammar correction ──
  const handleAccept = useCallback(() => {
    const mark = storedMarkRef.current;
    if (!mark || !mark.suggestion) return;

    const { from, to, suggestion } = mark;
    const state = editor.state;
    const tr = state.tr;
    tr.delete(from, to);
    tr.insert(from, state.schema.text(suggestion));
    editor.view.dispatch(tr);

    const id = `grammar-${from}-${to}`;
    acceptGrammarError(id);
    setVisible(false);
    storedMarkRef.current = null;
  }, [editor, acceptGrammarError]);

  // ── Reject grammar correction ──
  const handleReject = useCallback(() => {
    const mark = storedMarkRef.current;
    if (!mark) return;

    const { from, to } = mark;
    const state = editor.state;
    const markType = state.schema.marks.grammarError;
    const tr = state.tr.removeMark(from, to, markType);
    editor.view.dispatch(tr);

    const id = `grammar-${from}-${to}`;
    rejectGrammarError(id);
    setVisible(false);
    storedMarkRef.current = null;
  }, [editor, rejectGrammarError]);

  if (!visible) return null;

  const suggestion = storedMarkRef.current?.suggestion || '';
  const errorType = storedMarkRef.current?.errorType || 'grammar';

  const errorTypeLabels: Record<string, string> = {
    grammar: 'نحوي',
    style: 'صياغي',
    punctuation: 'ترقيم',
  };

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
      <div className="bg-white rounded-xl shadow-2xl border border-gray-200 w-[300px] overflow-hidden">
        {/* Header */}
        <div className="flex items-center justify-between px-3.5 py-2 bg-blue-50 border-b border-blue-100">
          <div className="flex items-center gap-1.5">
            <Ruler className="w-3.5 h-3.5 text-blue-500" />
            <span className="text-xs font-semibold text-blue-700">
              📐 تعديل {errorTypeLabels[errorType] || 'نحوي'}
            </span>
          </div>
          <button
            onClick={() => {
              setVisible(false);
              storedMarkRef.current = null;
            }}
            className="w-5 h-5 rounded flex items-center justify-center text-gray-400 hover:bg-blue-100 hover:text-blue-600 transition-colors"
          >
            <X className="w-3 h-3" />
          </button>
        </div>

        {/* Suggestion */}
        <div className="px-3.5 py-3">
          <div className="text-center mb-3">
            <span className="text-xs text-gray-400 uppercase tracking-wider">
              التعديل المقترح
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
              className="flex-1 flex items-center justify-center gap-1.5 px-3 py-2 rounded-lg bg-gradient-to-r from-blue-500 to-indigo-600 text-white text-xs font-semibold hover:from-blue-600 hover:to-indigo-700 transition-all shadow-sm"
            >
              <Check className="w-3.5 h-3.5" />
              قبول التعديل
            </button>
            <button
              onMouseDown={(e) => {
                e.preventDefault();
                handleReject();
              }}
              className="flex-1 flex items-center justify-center gap-1.5 px-3 py-2 rounded-lg bg-gray-100 text-gray-600 text-xs font-semibold hover:bg-gray-200 transition-all"
            >
              <X className="w-3.5 h-3.5" />
              التراجع
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
