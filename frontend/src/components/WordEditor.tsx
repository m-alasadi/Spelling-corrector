import { useState, useCallback, useEffect, useMemo } from 'react';
import type { Segment, WordDiff } from '../types';
import * as api from '../services/api';
import RibbonToolbar from './RibbonToolbar';
import CorrectionPopup from './CorrectionPopup';

interface WordEditorProps {
  jobId: string;
  segments: Segment[];
  filename: string;
  initialCorrectedCount: number;
}

interface PopupState {
  visible: boolean;
  segmentIndex: number;
  wordIndex: number;
  original: string;
  suggestion: string;
  position: { top: number; left: number };
}

export default function WordEditor({
  jobId,
  segments: initialSegments,
  filename,
  initialCorrectedCount,
}: WordEditorProps) {
  const [segments, setSegments] = useState<Segment[]>(initialSegments);
  const [popup, setPopup] = useState<PopupState>({
    visible: false,
    segmentIndex: 0,
    wordIndex: 0,
    original: '',
    suggestion: '',
    position: { top: 0, left: 0 },
  });
  const [isProcessing, setIsProcessing] = useState(false);

  // Calculate error count
  const errorCount = useMemo(() => {
    return segments.reduce((total, seg) => {
      const diffs = seg.word_diffs || [];
      return (
        total +
        diffs.filter(
          (w) => w.is_error && !w.accepted && !w.ignored && !w.merged
        ).length
      );
    }, 0);
  }, [segments]);

  const correctedCount = useMemo(() => {
    return segments.reduce((total, seg) => {
      const diffs = seg.word_diffs || [];
      return (
        total + diffs.filter((w) => w.is_error && (w.accepted || w.ignored)).length
      );
    }, 0);
  }, [segments]);

  // Handle click on error word
  const handleWordClick = useCallback(
    (segIdx: number, wordLocalIdx: number, event: React.MouseEvent) => {
      const seg = segments[segIdx];
      const diffs = seg.word_diffs || [];
      const wordDiffs = diffs.filter((d) => d.type === 'word' && !d.merged);
      const diff = wordDiffs[wordLocalIdx];

      if (diff && diff.is_error && !diff.accepted && !diff.ignored) {
        const rect = (event.target as HTMLElement).getBoundingClientRect();
        setPopup({
          visible: true,
          segmentIndex: segIdx,
          wordIndex: wordLocalIdx,
          original: diff.value,
          suggestion: diff.suggestion || '',
          position: {
            top: rect.bottom + 8,
            left: rect.left + rect.width / 2 - 160,
          },
        });
      }
    },
    [segments]
  );

  // Accept correction
  const handleAccept = useCallback(async () => {
    if (!popup.visible) return;
    const { segmentIndex, wordIndex } = popup;

    setSegments((prev) => {
      const next = [...prev];
      const seg = { ...next[segmentIndex] };
      const diffs = [...(seg.word_diffs || [])];
      const wordDiffs = diffs.filter((d) => d.type === 'word' && !d.merged);
      const targetDiff = wordDiffs[wordIndex];
      if (targetDiff) {
        const idx = diffs.indexOf(targetDiff);
        diffs[idx] = { ...targetDiff, accepted: true };
        seg.word_diffs = diffs;
        next[segmentIndex] = seg;
      }
      return next;
    });

    setPopup((p) => ({ ...p, visible: false }));

    try {
      await api.applyCorrection(jobId, segmentIndex, wordIndex, 'accept');
    } catch (e) {
      console.error('Failed to sync correction:', e);
    }
  }, [popup, jobId]);

  // Ignore correction
  const handleIgnore = useCallback(async () => {
    if (!popup.visible) return;
    const { segmentIndex, wordIndex } = popup;

    setSegments((prev) => {
      const next = [...prev];
      const seg = { ...next[segmentIndex] };
      const diffs = [...(seg.word_diffs || [])];
      const wordDiffs = diffs.filter((d) => d.type === 'word' && !d.merged);
      const targetDiff = wordDiffs[wordIndex];
      if (targetDiff) {
        const idx = diffs.indexOf(targetDiff);
        diffs[idx] = { ...targetDiff, ignored: true };
        seg.word_diffs = diffs;
        next[segmentIndex] = seg;
      }
      return next;
    });

    setPopup((p) => ({ ...p, visible: false }));

    try {
      await api.applyCorrection(jobId, segmentIndex, wordIndex, 'ignore');
    } catch (e) {
      console.error('Failed to sync ignore:', e);
    }
  }, [popup, jobId]);

  // Accept all
  const handleAcceptAll = useCallback(async () => {
    if (!confirm('قبول جميع التصحيحات المتبقية؟')) return;

    setSegments((prev) =>
      prev.map((seg) => ({
        ...seg,
        word_diffs: (seg.word_diffs || []).map((w) =>
          w.is_error && !w.accepted && !w.ignored
            ? { ...w, accepted: true }
            : w
        ),
      }))
    );

    try {
      await api.acceptAll(jobId);
    } catch (e) {
      console.error('Failed to accept all:', e);
    }
  }, [jobId]);

  // Ignore all
  const handleIgnoreAll = useCallback(async () => {
    if (!confirm('تجاهل جميع التصحيحات المتبقية؟')) return;

    setSegments((prev) =>
      prev.map((seg) => ({
        ...seg,
        word_diffs: (seg.word_diffs || []).map((w) =>
          w.is_error && !w.accepted && !w.ignored
            ? { ...w, ignored: true }
            : w
        ),
      }))
    );

    try {
      await api.ignoreAll(jobId);
    } catch (e) {
      console.error('Failed to ignore all:', e);
    }
  }, [jobId]);

  // Jump to next error
  const handleJumpNext = useCallback(() => {
    const firstError = document.querySelector('.spell-error');
    if (firstError) {
      firstError.scrollIntoView({ behavior: 'smooth', block: 'center' });
      (firstError as HTMLElement).click();
    }
  }, []);

  // Download
  const handleDownload = useCallback(() => {
    window.open(api.getDownloadUrl(jobId), '_blank');
  }, [jobId]);

  // Add word to dictionary
  const handleAddToDict = useCallback(async () => {
    if (!popup.visible) return;
    const { original, suggestion } = popup;

    try {
      await api.addToDictionary(original, suggestion);
      // Treat as "ignored" locally
      setSegments((prev) => {
        const next = [...prev];
        const seg = { ...next[popup.segmentIndex] };
        const diffs = [...(seg.word_diffs || [])];
        const wordDiffs = diffs.filter((d) => d.type === 'word' && !d.merged);
        const targetDiff = wordDiffs[popup.wordIndex];
        if (targetDiff) {
          const idx = diffs.indexOf(targetDiff);
          diffs[idx] = { ...targetDiff, ignored: true };
          seg.word_diffs = diffs;
          next[popup.segmentIndex] = seg;
        }
        return next;
      });
      setPopup((p) => ({ ...p, visible: false }));
      alert(`✅ تمت إضافة "${original}" إلى القاموس`);
    } catch (e) {
      console.error('Failed to add to dictionary:', e);
      alert('❌ فشلت الإضافة للقاموس');
    }
  }, [popup, jobId]);

  // Handle correction button
  const handleCorrect = useCallback(async () => {
    setIsProcessing(true);
    try {
      await api.correctFile(jobId);
      window.location.reload();
    } catch (e) {
      console.error('Correction failed:', e);
    } finally {
      setIsProcessing(false);
    }
  }, [jobId]);

  // Render a segment's tokens
  const renderSegmentTokens = (segIdx: number, diffs: WordDiff[]) => {
    let wordLocalIdx = 0;
    const elements: React.ReactNode[] = [];

    for (let i = 0; i < diffs.length; i++) {
      const token = diffs[i];

      if (token.type === 'word') {
        if (token.merged) continue;

        const idx = wordLocalIdx;
        wordLocalIdx++;

        if (token.is_error && !token.accepted && !token.ignored) {
          // Error word - red wavy underline
          elements.push(
            <span
              key={`w-${segIdx}-${i}`}
              className="spell-error"
              onClick={(e) => handleWordClick(segIdx, idx, e)}
              title={`اقتراح: ${token.suggestion || '—'}`}
            >
              {token.value}
            </span>
          );
        } else if (token.accepted) {
          // Accepted word - green highlight
          elements.push(
            <span
              key={`w-${segIdx}-${i}`}
              className="bg-green-100 text-green-800 rounded px-0.5 font-medium"
            >
              {token.suggestion || token.value}
            </span>
          );
        } else if (token.ignored) {
          // Ignored word
          elements.push(
            <span key={`w-${segIdx}-${i}`} className="text-gray-400">
              {token.value}
            </span>
          );
        } else {
          // Normal word
          elements.push(
            <span key={`w-${segIdx}-${i}`}>{token.value}</span>
          );
        }
      } else {
        // Space or punctuation
        elements.push(
          <span key={`t-${segIdx}-${i}`}>{token.value}</span>
        );
      }
    }

    return elements;
  };

  return (
    <div className="min-h-screen bg-gray-100 flex flex-col">
      {/* Ribbon Toolbar */}
      <RibbonToolbar
        errorCount={errorCount}
        correctedCount={correctedCount}
        totalSegments={segments.length}
        isProcessing={isProcessing}
        onCorrect={handleCorrect}
        onAcceptAll={handleAcceptAll}
        onIgnoreAll={handleIgnoreAll}
        onDownload={handleDownload}
        onJumpNext={handleJumpNext}
      />

      {/* Canvas - A4 Paper */}
      <div className="flex-1 py-8 px-4">
        <div className="max-w-4xl mx-auto">
          <div className="bg-white rounded-xl shadow-lg border border-gray-200 overflow-hidden">
            {/* Paper Header */}
            <div className="flex items-center justify-between px-8 py-4 border-b border-gray-100 bg-gray-50/50">
              <h2 className="text-sm font-semibold text-gray-700">
                📄 {filename}
              </h2>
              <span className="text-xs text-gray-400">
                {errorCount === 0
                  ? '✅ تم التصحيح بالكامل'
                  : `${errorCount} أخطاء متبقية`}
              </span>
            </div>

            {/* Document Content */}
            <div
              className="p-12 min-h-[600px] leading-[2.2] text-gray-800"
              dir="rtl"
              style={{ fontFamily: "'Noto Naskh Arabic', Georgia, serif", fontSize: '20px' }}
            >
              {segments.length === 0 ? (
                <div className="text-center text-gray-400 py-20">
                  لا يوجد محتوى للعرض
                </div>
              ) : (
                segments.map((seg, segIdx) => {
                  const diffs = seg.word_diffs || [];
                  const segErrors = diffs.filter(
                    (w) => w.is_error && !w.accepted && !w.ignored && !w.merged
                  ).length;
                  const hasErrors = segErrors > 0;

                  return (
                    <div
                      key={seg.id}
                      className={`relative mb-1 py-2 px-4 rounded-lg border-r-3 transition-colors hover:bg-gray-50 ${
                        hasErrors
                          ? 'border-r-red-400'
                          : 'border-r-transparent'
                      }`}
                    >
                      {/* Segment Number */}
                      <span className="absolute -left-2 top-2 bg-indigo-100 text-indigo-700 text-[10px] font-bold px-2 py-0.5 rounded-r-lg font-sans min-w-[18px] text-center">
                        {seg.id}
                      </span>

                      {/* Speaker */}
                      {seg.speaker && (
                        <div className="text-[11px] text-gray-400 mb-1 font-sans flex items-center gap-1">
                          <span className="w-1 h-1 rounded-full bg-blue-500" />
                          {seg.speaker}
                        </div>
                      )}

                      {/* Text */}
                      <div className="font-arabic text-[20px] leading-[2.2]">
                        {renderSegmentTokens(segIdx, diffs)}
                      </div>
                    </div>
                  );
                })
              )}
            </div>
          </div>
        </div>
      </div>

      {/* Status Bar */}
      <div className="bg-white border-t border-gray-200 px-6 py-2 flex items-center justify-between text-xs text-gray-500">
        <div className="flex items-center gap-4">
          <span>{segments.length} مقاطع</span>
          <span>·</span>
          <span>{errorCount} أخطاء</span>
          <span>·</span>
          <span>{correctedCount} مقبولة</span>
        </div>
        <div className="flex items-center gap-4">
          <span>
            <kbd className="px-1.5 py-0.5 bg-gray-100 border border-gray-200 rounded text-[10px]">
              Tab
            </kbd>{' '}
            التالي
          </span>
          <span>
            <kbd className="px-1.5 py-0.5 bg-gray-100 border border-gray-200 rounded text-[10px]">
              Enter
            </kbd>{' '}
            قبول
          </span>
          <span>
            <kbd className="px-1.5 py-0.5 bg-gray-100 border border-gray-200 rounded text-[10px]">
              Esc
            </kbd>{' '}
            إغلاق
          </span>
        </div>
      </div>

      {/* Correction Popup */}
      {popup.visible && (
        <CorrectionPopup
          original={popup.original}
          suggestion={popup.suggestion}
          position={popup.position}
          onAccept={handleAccept}
          onIgnore={handleIgnore}
          onAddToDict={handleAddToDict}
          onClose={() => setPopup((p) => ({ ...p, visible: false }))}
        />
      )}
    </div>
  );
}
