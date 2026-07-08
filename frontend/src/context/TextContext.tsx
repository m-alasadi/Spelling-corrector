import { createContext, useContext, useState, useCallback, useRef } from 'react';
import type { ReactNode } from 'react';
import type { Segment } from '../types';

// ─── Types ───

export type AppStep = 'spell' | 'grammar';

export interface SpellErrorData {
  id: string;
  wordIndex: number;
  segmentId: number;
  original: string;
  suggestion: string;
  accepted: boolean;
  ignored: boolean;
}

export interface GrammarErrorData {
  id: string;
  original: string;
  suggestion: string;
  errorType: 'grammar' | 'style' | 'punctuation';
  accepted: boolean;
  rejected: boolean;
}

export interface GrammarOptions {
  addPunctuation: boolean;
  processingLevel: 'grammar-only' | 'full-fusha';
}

interface TextContextValue {
  // ── App State ──
  currentStep: AppStep;
  setCurrentStep: (step: AppStep) => void;

  // ── Job Info ──
  jobId: string | null;
  setJobId: (id: string | null) => void;
  filename: string;
  setFilename: (name: string) => void;

  // ── Segments (Spell Step) ──
  segments: Segment[];
  setSegments: (segments: Segment[]) => void;

  // ── Spell Errors ──
  spellErrors: SpellErrorData[];
  setSpellErrors: (errors: SpellErrorData[]) => void;
  acceptSpellError: (id: string) => void;
  ignoreSpellError: (id: string) => void;

  // ── Clean Text (output of spell step) ──
  cleanText: string;
  setCleanText: (text: string) => void;

  // ── Grammar Errors ──
  grammarErrors: GrammarErrorData[];
  setGrammarErrors: (errors: GrammarErrorData[]) => void;
  acceptGrammarError: (id: string) => void;
  rejectGrammarError: (id: string) => void;

  // ── Grammar Options ──
  grammarOptions: GrammarOptions;
  setGrammarOptions: (options: GrammarOptions) => void;

  // ── SSE State ──
  isStreaming: boolean;
  setIsStreaming: (v: boolean) => void;
  streamProgress: number;
  setStreamProgress: (v: number) => void;

  // ── Processing State ──
  isSpellProcessing: boolean;
  setIsSpellProcessing: (v: boolean) => void;
  isGrammarProcessing: boolean;
  setIsGrammarProcessing: (v: boolean) => void;

  // ── SSE Abort ──
  sseAbortRef: React.MutableRefObject<(() => void) | null>;

  // ── Helpers ──
  spellErrorCount: number;
  grammarErrorCount: number;
  canProceedToGrammar: boolean;
}

const TextContext = createContext<TextContextValue | null>(null);

export function TextProvider({ children }: { children: ReactNode }) {
  const [currentStep, setCurrentStep] = useState<AppStep>('spell');
  const [jobId, setJobId] = useState<string | null>(null);
  const [filename, setFilename] = useState('');
  const [segments, setSegments] = useState<Segment[]>([]);
  const [spellErrors, setSpellErrors] = useState<SpellErrorData[]>([]);
  const [cleanText, setCleanText] = useState('');
  const [grammarErrors, setGrammarErrors] = useState<GrammarErrorData[]>([]);
  const [grammarOptions, setGrammarOptions] = useState<GrammarOptions>({
    addPunctuation: false,
    processingLevel: 'grammar-only',
  });
  const [isStreaming, setIsStreaming] = useState(false);
  const [streamProgress, setStreamProgress] = useState(0);
  const [isSpellProcessing, setIsSpellProcessing] = useState(false);
  const [isGrammarProcessing, setIsGrammarProcessing] = useState(false);
  const sseAbortRef = useRef<(() => void) | null>(null);

  const acceptSpellError = useCallback((id: string) => {
    setSpellErrors((prev) =>
      prev.map((e) => (e.id === id ? { ...e, accepted: true } : e))
    );
  }, []);

  const ignoreSpellError = useCallback((id: string) => {
    setSpellErrors((prev) =>
      prev.map((e) => (e.id === id ? { ...e, ignored: true } : e))
    );
  }, []);

  const acceptGrammarError = useCallback((id: string) => {
    setGrammarErrors((prev) =>
      prev.map((e) => (e.id === id ? { ...e, accepted: true } : e))
    );
  }, []);

  const rejectGrammarError = useCallback((id: string) => {
    setGrammarErrors((prev) =>
      prev.map((e) => (e.id === id ? { ...e, rejected: true } : e))
    );
  }, []);

  // Computed values
  const spellErrorCount = spellErrors.filter(
    (e) => !e.accepted && !e.ignored
  ).length;

  const grammarErrorCount = grammarErrors.filter(
    (e) => !e.accepted && !e.rejected
  ).length;

  const canProceedToGrammar = !isStreaming && cleanText.length > 0;

  return (
    <TextContext.Provider
      value={{
        currentStep, setCurrentStep,
        jobId, setJobId,
        filename, setFilename,
        segments, setSegments,
        spellErrors, setSpellErrors,
        acceptSpellError, ignoreSpellError,
        cleanText, setCleanText,
        grammarErrors, setGrammarErrors,
        acceptGrammarError, rejectGrammarError,
        grammarOptions, setGrammarOptions,
        isStreaming, setIsStreaming,
        streamProgress, setStreamProgress,
        isSpellProcessing, setIsSpellProcessing,
        isGrammarProcessing, setIsGrammarProcessing,
        sseAbortRef,
        spellErrorCount,
        grammarErrorCount,
        canProceedToGrammar,
      }}
    >
      {children}
    </TextContext.Provider>
  );
}

export function useTextContext() {
  const ctx = useContext(TextContext);
  if (!ctx) {
    throw new Error('useTextContext must be used within a TextProvider');
  }
  return ctx;
}
