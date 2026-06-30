import { useState, useCallback, useRef } from 'react';
import type { JobData, Segment } from './types';
import type { SSEEvent } from './services/api';
import * as api from './services/api';
import UploadScreen from './components/UploadScreen';
import WordEditor from './components/WordEditor';

type AppState =
  | { screen: 'upload' }
  | { screen: 'editor'; jobId: string; segments: Segment[]; filename: string; correctedCount: number; totalErrors: number; isStreaming: boolean; progress: number };

function App() {
  const [state, setState] = useState<AppState>({ screen: 'upload' });
  const [uploadError, setUploadError] = useState<string | null>(null);
  const [isUploading, setIsUploading] = useState(false);
  const sseRef = useRef<{ abort: () => void } | null>(null);

  const handleUpload = useCallback(async (file: File) => {
    setIsUploading(true);
    setUploadError(null);

    try {
      // Step 1: Upload file (lightweight response)
      const uploadResult = await api.uploadFile(file);

      // Step 2: Open editor immediately with empty segments
      // (Segments will arrive via SSE init event)
      setState({
        screen: 'editor',
        jobId: uploadResult.job_id,
        segments: [],
        filename: uploadResult.filename,
        correctedCount: 0,
        totalErrors: 0,
        isStreaming: true,
        progress: 0,
      });

      // Step 3: Start SSE correction in background
      // Segments are received via the 'init' event
      let segments: Segment[] = [];

      sseRef.current = api.streamCorrection(
        uploadResult.job_id,
        (event: SSEEvent) => {
          if (event.type === 'init') {
            // Receive all segments from SSE
            segments = event.segments.map((s: any) => ({
              id: s.id,
              text_original: s.text_original || '',
              text_corrected: s.text_corrected || null,
              speaker: s.speaker || null,
              word_diffs: s.word_diffs || undefined,
              error_count: 0,
            }));
            setState((prev) => {
              if (prev.screen !== 'editor') return prev;
              return { ...prev, segments: [...segments] };
            });
          } else if (event.type === 'segment') {
            // Update a single segment with correction
            const idx = event.index;
            if (idx < segments.length) {
              segments[idx] = {
                ...segments[idx],
                text_corrected: event.text_corrected,
                word_diffs: event.word_diffs,
                error_count: event.error_count,
              };
              // Force re-render by creating new array
              setState((prev) => {
                if (prev.screen !== 'editor') return prev;
                const newSegs = [...segments];
                return {
                  ...prev,
                  segments: newSegs,
                };
              });
            }
          } else if (event.type === 'progress') {
            setState((prev) => {
              if (prev.screen !== 'editor') return prev;
              return {
                ...prev,
                progress: event.percent,
                correctedCount: event.corrected,
              };
            });
          } else if (event.type === 'done') {
            setState((prev) => {
              if (prev.screen !== 'editor') return prev;
              // Calculate final error count
              const totalErrors = segments.reduce((acc, seg) => {
                const diffs = seg.word_diffs || [];
                return acc + diffs.filter((w: any) => w.is_error && !w.accepted && !w.ignored && !w.merged).length;
              }, 0);
              return {
                ...prev,
                isStreaming: false,
                progress: 100,
                correctedCount: event.corrected_count,
                totalErrors,
              };
            });
          } else if (event.type === 'error') {
            console.error('SSE error:', event.message);
            setState((prev) => {
              if (prev.screen !== 'editor') return prev;
              return { ...prev, isStreaming: false };
            });
          }
        },
        (error) => {
          console.error('SSE connection error:', error);
          setState((prev) => {
            if (prev.screen !== 'editor') return prev;
            return { ...prev, isStreaming: false };
          });
        }
      );
    } catch (err: any) {
      const message =
        err.response?.data?.detail || err.message || 'حدث خطأ غير متوقع';
      setUploadError(message);
      setState({ screen: 'upload' });
    } finally {
      setIsUploading(false);
    }
  }, []);

  const handleBack = useCallback(() => {
    // Abort any running SSE
    if (sseRef.current) {
      sseRef.current.abort();
      sseRef.current = null;
    }
    setState({ screen: 'upload' });
  }, []);

  return (
    <div className="min-h-screen" dir="rtl">
      {state.screen === 'upload' && (
        <UploadScreen
          onUpload={handleUpload}
          isUploading={isUploading}
          error={uploadError}
        />
      )}

      {state.screen === 'editor' && (
        <WordEditor
          jobId={state.jobId}
          segments={state.segments}
          filename={state.filename}
          initialCorrectedCount={state.correctedCount}
          isStreaming={state.isStreaming}
          progress={state.progress}
          onBack={handleBack}
        />
      )}
    </div>
  );
}

export default App;
