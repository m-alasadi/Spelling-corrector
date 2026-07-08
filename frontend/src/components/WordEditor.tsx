import { useState, useCallback, useEffect, useMemo, useRef } from 'react';
import type { Segment, WordDiff, GrammarBatchResult, GrammarWordDiff } from '../types';
import * as api from '../services/api';
import RibbonToolbar from './RibbonToolbar';
import CorrectionPopup from './CorrectionPopup';

// Toast function
function showToast(message: string, type: 'ok' | 'info' | 'error' = 'ok') {
  const existing = document.querySelector('.custom-toast');
  if (existing) existing.remove();
  
  const toast = document.createElement('div');
  toast.className = `custom-toast fixed bottom-12 left-1/2 -translate-x-1/2 z-[2000] px-5 py-2.5 rounded-lg text-white text-sm font-medium shadow-lg transition-all duration-300 opacity-0 translate-y-4`;
  toast.style.background = type === 'ok' ? '#16a34a' : type === 'error' ? '#dc2626' : '#2563eb';
  toast.textContent = message;
  document.body.appendChild(toast);
  
  requestAnimationFrame(() => {
    toast.style.opacity = '1';
    toast.style.transform = 'translateX(-50%) translateY(0)';
  });
  
  setTimeout(() => {
    toast.style.opacity = '0';
    toast.style.transform = 'translateX(-50%) translateY(16px)';
    setTimeout(() => toast.remove(), 300);
  }, 2500);
}

interface WordEditorProps {
  jobId: string;
  segments: Segment[];
  filename: string;
  initialCorrectedCount: number;
  isStreaming: boolean;
  progress: number;
  onBack: () => void;
  /** Active editing mode */
  activeMode: 'spell' | 'grammar';
  /** Callback when mode changes */
  onModeChange: (mode: 'spell' | 'grammar') => void;
}

interface PopupState {
  visible: boolean;
  segmentIndex: number;
  wordIndex: number;
  original: string;
  suggestion: string;
  position: { top: number; left: number };
  type: 'spell' | 'grammar';
  segId?: number;
  grammarWordIdx?: number;
}

export default function WordEditor({
  jobId,
  segments: initialSegments,
  filename,
  initialCorrectedCount: _initialCorrectedCount,
  isStreaming,
  progress,
  onBack: _onBack,
  activeMode,
  onModeChange,
}: WordEditorProps) {
  const [segments, setSegments] = useState<Segment[]>(initialSegments);
  const [popup, setPopup] = useState<PopupState>({
    visible: false,
    segmentIndex: 0,
    wordIndex: 0,
    original: '',
    suggestion: '',
    position: { top: 0, left: 0 },
    type: 'spell',
  });
  const [isProcessing, setIsProcessing] = useState(false);
  const [grammarErrors, setGrammarErrors] = useState(0);
  const [isGrammarChecking, setIsGrammarChecking] = useState(false);
  const [grammarChecked, setGrammarChecked] = useState(false);
  const [_grammarResults, setGrammarResults] = useState<GrammarBatchResult[]>([]);
  const [grammarWordDiffs, setGrammarWordDiffs] = useState<Map<number, GrammarWordDiff[]>>(new Map());
  const [grammarAccepted, setGrammarAccepted] = useState<Set<string>>(new Set());
  const grammarCheckRun = useRef(false);

  // Sync segments from props (when SSE updates arrive)
  useEffect(() => {
    setSegments(initialSegments);
  }, [initialSegments]);

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

  // ─── Grammar Check: Auto-run on all segments when opening grammar tab ───
  useEffect(() => {
    if (activeMode !== 'grammar' || grammarChecked || isGrammarChecking || isStreaming) return;

    const runGrammarCheck = async () => {
      setIsGrammarChecking(true);
      try {
        // Build segments for batch check (use corrected text if available)
        const segsForCheck = segments
          .filter((s) => (s.text_corrected || s.text_original)?.trim())
          .map((s) => ({
            id: s.id,
            text: s.text_corrected || s.text_original,
          }));

        if (segsForCheck.length === 0) return;

        const result = await api.grammarCheckBatch(segsForCheck);

        // Compute word diffs for each grammar result
        const diffsMap = new Map<number, GrammarWordDiff[]>();
        let errorCount = 0;

        for (const r of result.results) {
          if (r.original !== r.corrected) {
            const diffs = computeGrammarDiff(r.original, r.corrected);
            diffsMap.set(r.id, diffs);
            errorCount += diffs.filter((d) => d.is_error).length;
          }
        }

        setGrammarResults(result.results);
        setGrammarWordDiffs(diffsMap);
        setGrammarErrors(errorCount);
        setGrammarChecked(true);
        grammarCheckRun.current = true;
      } catch (e) {
        console.error('Grammar batch check failed:', e);
      } finally {
        setIsGrammarChecking(false);
      }
    };

    runGrammarCheck();
  }, [activeMode, grammarChecked, isGrammarChecking, isStreaming, segments]);

  // Compute grammar word-level diff
  function computeGrammarDiff(original: string, corrected: string): GrammarWordDiff[] {
    const origTokens = original.split(/(\s+)/);
    const corrTokens = corrected.split(/(\s+)/);
    const diffs: GrammarWordDiff[] = [];

    for (let i = 0; i < origTokens.length; i++) {
      const orig = origTokens[i];
      const corr = corrTokens[i] || orig;
      if (orig.trim() === '') {
        diffs.push({ type: 'space', value: orig, is_error: false, suggestion: null });
      } else if (orig !== corr) {
        diffs.push({ type: 'word', value: orig, is_error: true, suggestion: corr });
      } else {
        diffs.push({ type: 'word', value: orig, is_error: false, suggestion: null });
      }
    }
    return diffs;
  }

  // Handle click on error word (spell OR grammar)
  const handleWordClick = useCallback(
    (segIdx: number, wordLocalIdx: number, event: React.MouseEvent, grammarInfo?: { segId: number; grammarIdx: number }) => {
      const rect = (event.target as HTMLElement).getBoundingClientRect();
      const pos = { top: rect.bottom + 8, left: rect.left + rect.width / 2 - 160 };

      // Grammar word click
      if (grammarInfo && activeMode === 'grammar') {
        const gDiff = grammarWordDiffs.get(grammarInfo.segId)?.[grammarInfo.grammarIdx];
        if (gDiff && gDiff.is_error && gDiff.suggestion) {
          setPopup({
            visible: true,
            segmentIndex: segIdx,
            wordIndex: wordLocalIdx,
            original: gDiff.value,
            suggestion: gDiff.suggestion,
            position: pos,
            type: 'grammar',
            segId: grammarInfo.segId,
            grammarWordIdx: grammarInfo.grammarIdx,
          });
          return;
        }
      }

      // Spell word click
      const seg = segments[segIdx];
      const diffs = seg.word_diffs || [];
      const wordDiffs = diffs.filter((d) => d.type === 'word' && !d.merged);
      const diff = wordDiffs[wordLocalIdx];

      if (diff && diff.is_error && !diff.accepted && !diff.ignored) {
        setPopup({
          visible: true,
          segmentIndex: segIdx,
          wordIndex: wordLocalIdx,
          original: diff.value,
          suggestion: diff.suggestion || '',
          position: pos,
          type: 'spell',
        });
      }
    },
    [segments, activeMode, grammarWordDiffs]
  );

  // Accept correction (spell or grammar)
  const handleAccept = useCallback(async () => {
    if (!popup.visible) return;
    const { segmentIndex, wordIndex, type, segId, grammarWordIdx } = popup;

    if (type === 'grammar' && segId !== undefined && grammarWordIdx !== undefined) {
      // Accept grammar correction: replace word in text AND update word_diffs
      const gDiff = grammarWordDiffs.get(segId)?.[grammarWordIdx];
      if (gDiff?.suggestion) {
        setGrammarAccepted((prev) => new Set([...prev, `${segId}-${grammarWordIdx}`]));
        setSegments((prev) =>
          prev.map((seg) => {
            if (seg.id !== segId) return seg;
            // Replace in text_corrected
            const text = seg.text_corrected || seg.text_original;
            const newText = text.replace(gDiff.value, gDiff.suggestion || '');
            // Update word_diffs: change the accepted word's value to suggestion, mark accepted
            const newDiffs = (seg.word_diffs || []).map((d) => {
              if (d.type === 'word' && d.value === gDiff.value && !d.accepted && !d.ignored) {
                return { ...d, value: gDiff.suggestion || d.value, accepted: true, suggestion: gDiff.suggestion };
              }
              return d;
            });
            return { ...seg, text_corrected: newText, word_diffs: newDiffs };
          })
        );
        showToast(`✅ تم التصحيح النحوي: ${gDiff.value} → ${gDiff.suggestion}`, 'ok');
      }
    } else {
      // Accept spell correction
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

      try {
        await api.applyCorrection(jobId, segmentIndex, wordIndex, 'accept');
      } catch (e) {
        console.error('Failed to sync correction:', e);
      }
    }

    setPopup((p) => ({ ...p, visible: false }));
  }, [popup, jobId, grammarWordDiffs]);

  // Ignore correction (spell or grammar)
  const handleIgnore = useCallback(async () => {
    if (!popup.visible) return;
    const { segmentIndex, wordIndex, type, segId, grammarWordIdx } = popup;

    if (type === 'grammar' && segId !== undefined && grammarWordIdx !== undefined) {
      // Reject grammar correction: mark as accepted (dismissed)
      setGrammarAccepted((prev) => new Set([...prev, `${segId}-${grammarWordIdx}`]));
    } else {
      // Ignore spell correction
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

      try {
        await api.applyCorrection(jobId, segmentIndex, wordIndex, 'ignore');
      } catch (e) {
        console.error('Failed to sync ignore:', e);
      }
    }

    setPopup((p) => ({ ...p, visible: false }));
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

  // Jump to next error (spell or grammar)
  const handleJumpNext = useCallback(() => {
    const selector = activeMode === 'grammar' ? '.grammar-error:not(.spell-error)' : '.spell-error';
    const firstError = document.querySelector(selector) || document.querySelector('.spell-error') || document.querySelector('.grammar-error');
    if (firstError) {
      firstError.scrollIntoView({ behavior: 'smooth', block: 'center' });
      (firstError as HTMLElement).click();
    }
  }, [activeMode]);

  // Download
  const handleDownload = useCallback(() => {
    window.open(api.getDownloadUrl(jobId), '_blank');
  }, [jobId]);

  // Manual correction (user types the correction)
  const handleManualCorrect = useCallback(async (correctedText: string) => {
    if (!popup.visible) return;
    const { segmentIndex, wordIndex, original } = popup;
    const seg = segments[segmentIndex];
    const context = seg.text_original || '';

    try {
      // Save to database + dictionary
      await api.saveCorrection(original, correctedText, context, 'user');

      // Update local state
      setSegments((prev) => {
        const next = [...prev];
        const s = { ...next[segmentIndex] };
        const d = [...(s.word_diffs || [])];
        const wd = d.filter((x) => x.type === 'word' && !x.merged);
        const target = wd[wordIndex];
        if (target) {
          const idx = d.indexOf(target);
          d[idx] = { ...target, accepted: true, suggestion: correctedText };
          s.word_diffs = d;
          next[segmentIndex] = s;
        }
        return next;
      });

      setPopup((p) => ({ ...p, visible: false }));
      showToast(`✅ تم حفظ التصحيح: ${original} → ${correctedText}`, 'ok');
    } catch (e) {
      console.error('Failed to save manual correction:', e);
      showToast('❌ فشل حفظ التصحيح', 'error');
    }
  }, [popup, segments, jobId]);

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

  // Render a segment's tokens (with grammar underline support)
  const renderSegmentTokens = (segIdx: number, diffs: WordDiff[]) => {
    const seg = segments[segIdx];
    const segId = seg?.id;
    const gDiffs = grammarWordDiffs.get(segId);
    const isGrammarMode = activeMode === 'grammar' && gDiffs && gDiffs.length > 0;

    let wordLocalIdx = 0;
    const elements: React.ReactNode[] = [];

    // Build a lookup of grammar errors by word value for fast matching
    const grammarErrorMap = new Map<string, { suggestion: string; gIdx: number }>();
    if (isGrammarMode && gDiffs) {
      gDiffs.forEach((gd, gi) => {
        if (gd.type === 'word' && gd.is_error && gd.suggestion) {
          // Store first occurrence of each error word
          if (!grammarErrorMap.has(gd.value)) {
            grammarErrorMap.set(gd.value, { suggestion: gd.suggestion, gIdx: gi });
          }
        }
      });
    }

    for (let i = 0; i < diffs.length; i++) {
      const token = diffs[i];

      if (token.type === 'word') {
        if (token.merged) continue;

        const idx = wordLocalIdx;
        wordLocalIdx++;

        // Check for grammar error by matching word VALUE (not index)
        let hasGrammarError = false;
        let grammarSuggestion = '';
        let grammarMatchIdx = -1;
        if (isGrammarMode) {
          const match = grammarErrorMap.get(token.value);
          if (match && !grammarAccepted.has(`${segId}-${match.gIdx}`)) {
            hasGrammarError = true;
            grammarSuggestion = match.suggestion;
            grammarMatchIdx = match.gIdx;
          }
        }

        // Determine CSS class
        let className = '';
        if (token.is_error && !token.accepted && !token.ignored) {
          className = 'spell-error';
          if (hasGrammarError) className += ' grammar-error';
        } else if (hasGrammarError) {
          className = 'grammar-error';
        } else if (token.accepted) {
          className = 'bg-green-100 text-green-800 rounded px-0.5 font-medium';
        } else if (token.ignored) {
          className = 'text-gray-400';
        }

        if (token.is_error && !token.accepted && !token.ignored) {
          // Spell error (may also have grammar error)
          elements.push(
            <span
              key={`w-${segIdx}-${i}`}
              className={className}
              onClick={(e) => handleWordClick(segIdx, idx, e)}
              title={hasGrammarError ? `نحوي: ${grammarSuggestion}` : `اقتراح: ${token.suggestion || '—'}`}
            >
              {token.value}
            </span>
          );
        } else if (hasGrammarError) {
          // Grammar-only error: clickable
          elements.push(
            <span
              key={`w-${segIdx}-${i}`}
              className={className}
              onClick={(e) => handleWordClick(segIdx, idx, e, { segId, grammarIdx: grammarMatchIdx })}
              title={`تصحيح نحوي: ${grammarSuggestion}`}
            >
              {token.value}
            </span>
          );
        } else if (token.accepted) {
          elements.push(
            <span
              key={`w-${segIdx}-${i}`}
              className={className}
            >
              {token.suggestion || token.value}
            </span>
          );
        } else if (token.ignored) {
          elements.push(
            <span key={`w-${segIdx}-${i}`} className={className}>
              {token.value}
            </span>
          );
        } else {
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
        activeMode={activeMode}
        onModeChange={onModeChange}
        grammarErrorCount={grammarErrors}
      />

      {/* Streaming Progress Bar */}
      {isStreaming && (
        <div className="bg-blue-50 border-b border-blue-200 px-6 py-3">
          <div className="max-w-4xl mx-auto flex items-center gap-4">
            <div className="w-5 h-5 border-2 border-blue-500 border-t-transparent rounded-full animate-spin shrink-0" />
            <div className="flex-1">
              <div className="flex items-center justify-between mb-1">
                <span className="text-sm font-medium text-blue-700">جاري التصحيح...</span>
                <span className="text-xs text-blue-500">{progress}% — {correctedCount} مقطع تم تصحيحه</span>
              </div>
              <div className="w-full bg-blue-200 rounded-full h-1.5">
                <div className="bg-blue-500 h-1.5 rounded-full transition-all duration-300" style={{ width: `${progress}%` }} />
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Main Layout */}
      <div className="flex-1 overflow-y-auto py-8 px-4">
        <div className="max-w-4xl mx-auto">
          <div className="bg-white rounded-xl shadow-lg border border-gray-200 overflow-hidden">
            {/* Paper Header */}
            <div className="flex items-center justify-between px-8 py-4 border-b border-gray-100 bg-gray-50/50">
              <div className="flex items-center gap-3">
                <h2 className="text-sm font-semibold text-gray-700">📄 {filename}</h2>
                {isStreaming && (
                  <span className="text-xs bg-blue-100 text-blue-600 px-2 py-0.5 rounded-full animate-pulse">جاري التصحيح</span>
                )}
              </div>
              <span className="text-xs text-gray-400">
                {isStreaming ? `${progress}% مكتمل` : errorCount === 0 ? '✅ تم التصحيح بالكامل' : `${errorCount} أخطاء متبقية`}
              </span>
            </div>

            {/* Document Content */}
            <div className="p-12 min-h-[600px] leading-[2.2] text-gray-800" dir="rtl" style={{ fontFamily: "'Noto Naskh Arabic', Georgia, serif", fontSize: '20px' }}>
              {segments.length === 0 ? (
                <div className="text-center text-gray-400 py-20">لا يوجد محتوى للعرض</div>
              ) : (
                segments.map((seg, segIdx) => {
                  const diffs = seg.word_diffs || [];
                  const segErrors = diffs.filter((w) => w.is_error && !w.accepted && !w.ignored && !w.merged).length;
                  const hasErrors = segErrors > 0;
                  return (
                    <div key={seg.id} className={`relative mb-1 py-2 px-4 rounded-lg border-r-3 transition-colors hover:bg-gray-50 ${hasErrors ? 'border-r-red-400' : 'border-r-transparent'}`}>
                      <span className="absolute -left-2 top-2 bg-indigo-100 text-indigo-700 text-[10px] font-bold px-2 py-0.5 rounded-r-lg font-sans min-w-[18px] text-center">{seg.id}</span>
                      {seg.speaker && (
                        <div className="text-[11px] text-gray-400 mb-1 font-sans flex items-center gap-1">
                          <span className="w-1 h-1 rounded-full bg-blue-500" />
                          {seg.speaker}
                        </div>
                      )}
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
          <span><kbd className="px-1.5 py-0.5 bg-gray-100 border border-gray-200 rounded text-[10px]">Tab</kbd> التالي</span>
          <span><kbd className="px-1.5 py-0.5 bg-gray-100 border border-gray-200 rounded text-[10px]">Enter</kbd> قبول</span>
          <span><kbd className="px-1.5 py-0.5 bg-gray-100 border border-gray-200 rounded text-[10px]">Esc</kbd> إغلاق</span>
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
          onManualCorrect={handleManualCorrect}
          onClose={() => setPopup((p) => ({ ...p, visible: false }))}
        />
      )}
    </div>
  );
}
