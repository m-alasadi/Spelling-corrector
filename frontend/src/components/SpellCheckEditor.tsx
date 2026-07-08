import { useEffect, useCallback, useRef } from 'react';
import { useEditor, EditorContent } from '@tiptap/react';
import StarterKit from '@tiptap/starter-kit';
import Underline from '@tiptap/extension-underline';
import Placeholder from '@tiptap/extension-placeholder';
import { SpellErrorMark } from '../extensions';
import SpellBubbleMenu from './SpellBubbleMenu';
import { useTextContext } from '../context/TextContext';
import type { Segment, WordDiff } from '../types';
import * as api from '../services/api';
import { Loader2, CheckCircle, AlertCircle, ArrowDown, CheckCheck } from 'lucide-react';

// ── Helper: Escape HTML special chars ──
function escapeHtml(str: string): string {
  return str
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#039;');
}

export default function SpellCheckEditor() {
  const {
    jobId,
    segments,
    setSegments,
    setSpellErrors,
    setCleanText,
    isStreaming,
    setIsStreaming,
    streamProgress,
    setStreamProgress,
    setIsSpellProcessing,
    spellErrorCount,
  } = useTextContext();

  const hasRunRef = useRef(false);

  const editor = useEditor({
    extensions: [
      StarterKit.configure({
        heading: false,
        codeBlock: false,
        blockquote: false,
        horizontalRule: false,
      }),
      Underline,
      SpellErrorMark,
      Placeholder.configure({
        placeholder: 'في انتظار تحميل النص...',
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

  // ── Build editor content WITH spell error marks ──
  const buildEditorContent = useCallback(
    (segs: Segment[]) => {
      if (!editor || segs.length === 0) return;

      // Build HTML with spell error marks inline
      const html = segs
        .map((seg) => {
          const diffs = seg.word_diffs || [];
          let wordIdx = 0;
          let textHtml = '';

          if (diffs.length > 0) {
            // Build text from word_diffs with marks for errors
            for (const diff of diffs) {
              if (diff.type === 'word') {
                const escaped = escapeHtml(diff.value);
                if (diff.is_error && !diff.accepted && !diff.ignored && !diff.merged) {
                  // Error word — wrap with spell-error mark
                  textHtml += `<span data-spell-error="true" data-suggestion="${escapeHtml(diff.suggestion || '')}" data-word-index="${wordIdx}" data-segment-id="${seg.id}" class="spell-error">${escaped}</span>`;
                } else if (diff.accepted) {
                  // Accepted correction — green highlight
                  textHtml += `<span class="bg-green-100 text-green-800 rounded px-0.5 font-medium">${escapeHtml(diff.suggestion || diff.value)}</span>`;
                } else if (diff.ignored) {
                  textHtml += `<span class="text-gray-400">${escaped}</span>`;
                } else {
                  textHtml += escaped;
                }
                wordIdx++;
              } else {
                // Space or punctuation — render as-is
                textHtml += escapeHtml(diff.value);
              }
            }
          } else {
            textHtml = escapeHtml(seg.text_original || '');
          }

          return `<div class="segment-block" data-segment-id="${seg.id}">
          <span class="seg-number">${seg.id}</span>
          ${seg.speaker ? `<div class="seg-speaker">${seg.speaker}</div>` : ''}
          <div class="seg-text">${textHtml || '—'}</div>
        </div>`;
        })
        .join('');

      editor.commands.setContent(html);
    },
    [editor]
  );

  // ── Collect spell errors from segments (for context state) ──
  const collectSpellErrors = useCallback(
    (segs: Segment[]) => {
      const errors: Array<{
        id: string;
        wordIndex: number;
        segmentId: number;
        original: string;
        suggestion: string;
        accepted: boolean;
        ignored: boolean;
      }> = [];

      segs.forEach((seg) => {
        if (!seg.word_diffs) return;
        let wordIdx = 0;
        seg.word_diffs.forEach((diff) => {
          if (diff.type === 'word') {
            if (diff.is_error && !diff.accepted && !diff.ignored && !diff.merged) {
              errors.push({
                id: `spell-${seg.id}-${wordIdx}`,
                wordIndex: wordIdx,
                segmentId: seg.id,
                original: diff.value,
                suggestion: diff.suggestion || '',
                accepted: false,
                ignored: false,
              });
            }
            wordIdx++;
          }
        });
      });

      setSpellErrors(errors);
    },
    [setSpellErrors]
  );

  // ── Fetch job data and run spell check ──
  const fetchAndCheck = useCallback(async () => {
    if (!jobId || hasRunRef.current) return;
    hasRunRef.current = true;

    setIsStreaming(true);
    setIsSpellProcessing(true);
    setStreamProgress(10);

    try {
      // Step 1: Get job data (segments)
      const jobData = await api.getJobData(jobId);
      const rawSegments: Segment[] = jobData.data.segments.map((s: any) => ({
        id: s.id,
        text_original: s.text_original || '',
        text_corrected: s.text_corrected || null,
        speaker: s.speaker || null,
        word_diffs: s.word_diffs || undefined,
        error_count: s.error_count || 0,
      }));

      setSegments(rawSegments);
      buildEditorContent(rawSegments);
      setStreamProgress(30);

      // Step 2: Run spell check batch
      const segsForCheck = rawSegments
        .filter((s) => s.text_original.trim())
        .map((s) => ({ id: s.id, text: s.text_original }));

      if (segsForCheck.length === 0) {
        setIsStreaming(false);
        setIsSpellProcessing(false);
        setStreamProgress(100);
        return;
      }

      setStreamProgress(50);
      const result = await api.stage1SpellCheckBatch(segsForCheck);
      setStreamProgress(80);

      // Step 3: Merge results back into segments
      const updatedSegments = rawSegments.map((seg) => {
        const match = result.results.find((r) => r.id === seg.id);
        if (match) {
          return {
            ...seg,
            text_corrected: match.corrected,
            word_diffs: match.word_diffs as WordDiff[],
            error_count: match.word_diffs.filter((w: any) => w.is_error).length,
          };
        }
        return seg;
      });

      setSegments(updatedSegments);
      buildEditorContent(updatedSegments);
      collectSpellErrors(updatedSegments);

      // Build clean text
      const clean = updatedSegments
        .map((s) => s.text_corrected || s.text_original)
        .join('\n');
      setCleanText(clean);

      setStreamProgress(100);
    } catch (err) {
      console.error('Spell check failed:', err);
    } finally {
      setIsStreaming(false);
      setIsSpellProcessing(false);
    }
  }, [
    jobId,
    setSegments,
    buildEditorContent,
    collectSpellErrors,
    setIsStreaming,
    setIsSpellProcessing,
    setStreamProgress,
    setCleanText,
  ]);

  // ── Auto-fetch when component mounts ──
  useEffect(() => {
    if (jobId && segments.length === 0 && !hasRunRef.current) {
      fetchAndCheck();
    }
  }, [jobId, segments.length, fetchAndCheck]);

  // ── Jump to next error ──
  const jumpToNextError = useCallback(() => {
    if (!editor) return;
    const el = document.querySelector('.spell-error');
    if (el) {
      el.scrollIntoView({ behavior: 'smooth', block: 'center' });
    }
  }, [editor]);

  // ── Accept all corrections ──
  const handleAcceptAll = useCallback(() => {
    if (!editor) return;

    // Update all segments: accept all error word_diffs
    const updatedSegments = segments.map((seg) => ({
      ...seg,
      text_corrected: seg.text_corrected || seg.text_original,
      word_diffs: (seg.word_diffs || []).map((d) =>
        d.is_error ? { ...d, accepted: true } : d
      ),
      error_count: 0,
    }));

    setSegments(updatedSegments);
    setSpellErrors([]);

    // Rebuild editor with corrected text (no error marks)
    const html = updatedSegments
      .map((seg) => {
        const text = seg.text_corrected || seg.text_original || '';
        return `<div class="segment-block" data-segment-id="${seg.id}">
          <span class="seg-number">${seg.id}</span>
          ${seg.speaker ? `<div class="seg-speaker">${seg.speaker}</div>` : ''}
          <div class="seg-text">${escapeHtml(text) || '—'}</div>
        </div>`;
      })
      .join('');
    editor.commands.setContent(html);

    // Update clean text
    const clean = updatedSegments
      .map((s) => s.text_corrected || s.text_original)
      .join('\n');
    setCleanText(clean);
  }, [editor, segments, setSegments, setSpellErrors, setCleanText]);

  // ── Listen for accept-all event from sidebar ──
  useEffect(() => {
    const handler = () => handleAcceptAll();
    window.addEventListener('spell-accept-all', handler);
    return () => window.removeEventListener('spell-accept-all', handler);
  }, [handleAcceptAll]);

  return (
    <div className="flex-1 flex flex-col overflow-hidden">
      {/* Progress Bar */}
      {isStreaming && (
        <div className="bg-blue-50 border-b border-blue-200 px-6 py-3">
          <div className="max-w-4xl mx-auto flex items-center gap-4">
            <Loader2 className="w-5 h-5 text-blue-500 animate-spin shrink-0" />
            <div className="flex-1">
              <div className="flex items-center justify-between mb-1">
                <span className="text-sm font-medium text-blue-700">
                  جاري التدقيق الإملائي...
                </span>
                <span className="text-xs text-blue-500">{streamProgress}%</span>
              </div>
              <div className="w-full bg-blue-200 rounded-full h-1.5">
                <div
                  className="bg-blue-500 h-1.5 rounded-full transition-all duration-300"
                  style={{ width: `${streamProgress}%` }}
                />
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Editor Stats */}
      <div className="bg-gray-50 border-b border-gray-200 px-6 py-2">
        <div className="max-w-4xl mx-auto flex items-center justify-between">
          <div className="flex items-center gap-4">
            <div className="flex items-center gap-1.5">
              {spellErrorCount > 0 ? (
                <AlertCircle className="w-4 h-4 text-red-500" />
              ) : (
                <CheckCircle className="w-4 h-4 text-green-500" />
              )}
              <span className="text-xs font-medium text-gray-600">
                {spellErrorCount} أخطاء إملائية
              </span>
            </div>
            <span className="text-xs text-gray-400">
              {segments.length} مقاطع
            </span>
          </div>
          <div className="flex items-center gap-2">
            {spellErrorCount > 0 && (
              <>
                <button
                  onClick={handleAcceptAll}
                  className="flex items-center gap-1 px-3 py-1.5 text-xs font-medium text-green-700 bg-green-50 hover:bg-green-100 border border-green-200 rounded-lg transition-colors"
                >
                  <CheckCheck className="w-3.5 h-3.5" />
                  قبول الكل
                </button>
                <button
                  onClick={jumpToNextError}
                  className="flex items-center gap-1 text-xs text-blue-600 hover:text-blue-800 transition-colors"
                >
                  <ArrowDown className="w-3.5 h-3.5" />
                  الخطأ التالي
                </button>
              </>
            )}
          </div>
        </div>
      </div>

      {/* Tiptap Editor */}
      <div className="flex-1 overflow-y-auto py-6 px-4">
        <div className="max-w-4xl mx-auto bg-white rounded-xl shadow-lg border border-gray-200 p-10 min-h-[500px]">
          {editor && <SpellBubbleMenu editor={editor} />}
          <EditorContent editor={editor} />
        </div>
      </div>
    </div>
  );
}
