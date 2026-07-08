import { useEffect, useCallback, useRef } from 'react';
import { useEditor, EditorContent } from '@tiptap/react';
import StarterKit from '@tiptap/starter-kit';
import Underline from '@tiptap/extension-underline';
import Placeholder from '@tiptap/extension-placeholder';
import { GrammarErrorMark } from '../extensions';
import GrammarBubbleMenu from './GrammarBubbleMenu';
import { useTextContext } from '../context/TextContext';
import { CheckCircle, AlertCircle, ArrowDown } from 'lucide-react';

export default function GrammarEditor() {
  const {
    cleanText,
    grammarErrors,
    grammarErrorCount,
    isGrammarProcessing,
  } = useTextContext();
  const contentSetRef = useRef(false);

  const editor = useEditor({
    extensions: [
      StarterKit.configure({
        heading: false,
        codeBlock: false,
        blockquote: false,
        horizontalRule: false,
      }),
      Underline,
      GrammarErrorMark,
      Placeholder.configure({
        placeholder: 'اضغط "تشغيل المعالجة المتقدمة" لبدء التدقيق النحوي...',
      }),
    ],
    editorProps: {
      attributes: {
        class: 'tiptap font-arabic focus:outline-none',
        dir: 'rtl',
        style:
          "font-family: 'Noto Naskh Arabic', Georgia, serif; font-size: 18px; line-height: 2.2;",
      },
    },
    editable: true,
  });

  // ── Set initial content from clean text ──
  useEffect(() => {
    if (!editor || !cleanText || contentSetRef.current) return;

    const paragraphs = cleanText.split('\n').filter((p) => p.trim());
    const html = paragraphs
      .map(
        (p, idx) =>
          `<div class="segment-block" data-segment-id="${idx + 1}">
            <span class="seg-number">${idx + 1}</span>
            <div class="seg-text">${p}</div>
          </div>`
      )
      .join('');

    editor.commands.setContent(html);
    contentSetRef.current = true;
  }, [editor, cleanText]);

  // ── Apply grammar error marks when grammar errors change ──
  useEffect(() => {
    if (!editor || grammarErrors.length === 0) return;

    // Wait for content to be set
    if (!contentSetRef.current) return;

    // Apply grammar error marks
    const applyMarks = () => {
      grammarErrors.forEach((error) => {
        if (error.accepted || error.rejected) return;

        // Search for the error text in the editor
        const doc = editor.state.doc;
        let found = false;

        doc.descendants((node, pos) => {
          if (found) return false;
          if (!node.isText) return true;

          const text = node.text || '';
          const idx = text.indexOf(error.original);
          if (idx !== -1) {
            const from = pos + idx;
            const to = from + error.original.length;
            editor.chain()
              .setTextSelection({ from, to })
              .setGrammarError({
                suggestion: error.suggestion,
                errorType: error.errorType,
              })
              .run();
            found = true;
            return false;
          }
          return true;
        });
      });
    };

    // Small delay to ensure DOM is ready
    requestAnimationFrame(applyMarks);
  }, [editor, grammarErrors]);

  // ── Jump to next error ──
  const jumpToNextError = useCallback(() => {
    if (!editor) return;
    const el = document.querySelector('.grammar-error');
    if (el) {
      el.scrollIntoView({ behavior: 'smooth', block: 'center' });
    }
  }, [editor]);

  return (
    <div className="flex-1 flex flex-col overflow-hidden">
      {/* Stats Bar */}
      <div className="bg-gray-50 border-b border-gray-200 px-6 py-2">
        <div className="max-w-4xl mx-auto flex items-center justify-between">
          <div className="flex items-center gap-4">
            <div className="flex items-center gap-1.5">
              {isGrammarProcessing ? (
                <div className="w-4 h-4 border-2 border-blue-500 border-t-transparent rounded-full animate-spin" />
              ) : grammarErrorCount > 0 ? (
                <AlertCircle className="w-4 h-4 text-blue-500" />
              ) : (
                <CheckCircle className="w-4 h-4 text-green-500" />
              )}
              <span className="text-xs font-medium text-gray-600">
                {isGrammarProcessing
                  ? 'جاري التدقيق النحوي...'
                  : `${grammarErrorCount} تعديلات نحوية`}
              </span>
            </div>
          </div>
          {grammarErrorCount > 0 && (
            <button
              onClick={jumpToNextError}
              className="flex items-center gap-1 text-xs text-blue-600 hover:text-blue-800 transition-colors"
            >
              <ArrowDown className="w-3.5 h-3.5" />
              التعديل التالي
            </button>
          )}
        </div>
      </div>

      {/* Tiptap Editor */}
      <div className="flex-1 overflow-y-auto py-6 px-4">
        <div className="max-w-4xl mx-auto bg-white rounded-xl shadow-lg border border-gray-200 p-10 min-h-[500px]">
          {editor && <GrammarBubbleMenu editor={editor} />}
          <EditorContent editor={editor} />
        </div>
      </div>
    </div>
  );
}
