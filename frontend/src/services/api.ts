import axios from 'axios';
import type {
  UploadResponse,
  CorrectResponse,
  ApplyResponse,
  DictStats,
  HealthResponse,
  JobData,
} from '../types';

const API_BASE = '';  // Use Vite proxy in dev, or set to 'http://localhost:8000' for production

const api = axios.create({
  baseURL: API_BASE,
  timeout: 300000, // 5 minutes for large files
});

// ─── Upload File ───
export async function uploadFile(file: File): Promise<UploadResponse> {
  const formData = new FormData();
  formData.append('file', file);
  const { data } = await api.post<UploadResponse>('/upload', formData);
  return data;
}

// ─── Run Correction ───
export async function correctFile(
  jobId: string,
  model: string = 'gpt-4o-mini'
): Promise<CorrectResponse> {
  const { data } = await api.post<CorrectResponse>(
    `/correct/${jobId}?model=${model}`
  );
  return data;
}

// ─── Get Job Data (with word_diffs) ───
export async function getJobData(jobId: string): Promise<{
  job_id: string;
  filename: string;
  status: string;
  corrected_count: number;
  total_errors: number;
  data: JobData;
}> {
  const { data } = await api.get(`/api/job/${jobId}`);
  return data;
}

// ─── Apply Single Correction ───
export async function applyCorrection(
  jobId: string,
  segmentIndex: number,
  wordIndex: number,
  action: 'accept' | 'ignore'
): Promise<ApplyResponse> {
  const { data } = await api.post<ApplyResponse>('/api/apply', {
    job_id: jobId,
    segment_index: segmentIndex,
    word_index: wordIndex,
  action,
  });
  return data;
}

// ─── Accept All ───
export async function acceptAll(jobId: string): Promise<{ success: boolean }> {
  const { data } = await api.post('/api/accept-all', { job_id: jobId });
  return data;
}

// ─── Ignore All ───
export async function ignoreAll(jobId: string): Promise<{ success: boolean }> {
  const { data } = await api.post('/api/ignore-all', { job_id: jobId });
  return data;
}

// ─── Download ───
export function getDownloadUrl(jobId: string): string {
  return `${API_BASE}/api/download/${jobId}`;
}

// ─── Dictionary Stats ───
export async function getDictStats(): Promise<DictStats> {
  const { data } = await api.get<DictStats>('/api/dictionary');
  return data;
}

// ─── Add Word to Dictionary ───
export async function addToDictionary(
  word: string,
  correction?: string
): Promise<{ success: boolean; word: string; message: string }> {
  const { data } = await api.post('/api/dictionary/add', {
    word,
    correction: correction || null,
  });
  return data;
}

// ─── Save Correction (AI or User Manual) ───
export async function saveCorrection(
  original: string,
  corrected: string,
  context: string = '',
  source: 'ai' | 'user' = 'user'
): Promise<{ success: boolean; message: string }> {
  const { data } = await api.post('/api/corrections/save', {
    original,
    corrected,
    context,
    source,
  });
  return data;
}

// ─── Get Correction Stats ───
export async function getCorrectionStats(): Promise<{
  total_rules: number;
  total_frequency: number;
  user_corrections: number;
  ai_corrections: number;
}> {
  const { data } = await api.get('/api/corrections/stats');
  return data;
}

// ─── Get Common Errors ───
export async function getCommonErrors(minFrequency: number = 2): Promise<{
  errors: Array<{ original: string; corrected: string; frequency: number }>;
}> {
  const { data } = await api.get('/api/corrections/common', {
    params: { min_frequency: minFrequency },
  });
  return data;
}

// ─── Cache Stats ───
export async function getCacheStats(): Promise<{
  total_cached: number;
  memory_cached: number;
}> {
  const { data } = await api.get('/api/cache/stats');
  return data;
}

// ─── SSE: Real-time correction streaming ──

export interface SSEInitEvent {
  type: 'init';
  segments: Array<{
    id: number;
    text_original: string;
    text_corrected: string | null;
    speaker: string | null;
    word_diffs: any[] | null;
  }>;
  filename: string;
}

export interface SSESegmentEvent {
  type: 'segment';
  index: number;
  text_corrected: string;
  word_diffs: any[];
  error_count: number;
}

export interface SSEProgressEvent {
  type: 'progress';
  current: number;
  total: number;
  percent: number;
  corrected: number;
}

export interface SSEDoneEvent {
  type: 'done';
  corrected_count: number;
  total_segments: number;
  stats: any;
}

export interface SSEErrorEvent {
  type: 'error';
  message: string;
}

export type SSEEvent = SSEInitEvent | SSESegmentEvent | SSEProgressEvent | SSEDoneEvent | SSEErrorEvent;

/**
 * Connect to SSE correction stream.
 * Returns an object with onEvent callback and abort controller.
 */
export function streamCorrection(
  jobId: string,
  onEvent: (event: SSEEvent) => void,
  onError?: (error: Error) => void
): { abort: () => void } {
  const controller = new AbortController();
  
  const url = `${API_BASE}/correct-stream/${jobId}`;
  
  fetch(url, { signal: controller.signal })
    .then(async (response) => {
      if (!response.ok) {
        throw new Error(`HTTP ${response.status}`);
      }
      
      const reader = response.body?.getReader();
      if (!reader) throw new Error('No response body');
      
      const decoder = new TextDecoder();
      let buffer = '';
      
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        
        buffer += decoder.decode(value, { stream: true });
        
        // Parse SSE events (separated by \n\n)
        const lines = buffer.split('\n');
        buffer = lines.pop() || '';  // Keep incomplete line in buffer
        
        for (const line of lines) {
          if (line.startsWith('data: ')) {
            try {
              const data = JSON.parse(line.slice(6));
              onEvent(data);
            } catch (e) {
              // Ignore malformed JSON
            }
          }
        }
      }
    })
    .catch((error) => {
      if (error.name !== 'AbortError') {
        onError?.(error);
      }
    });
  
  return { abort: () => controller.abort() };
}

// ─── Health Check ───
export async function checkHealth(): Promise<HealthResponse> {
  const { data } = await api.get<HealthResponse>('/health');
  return data;
}
