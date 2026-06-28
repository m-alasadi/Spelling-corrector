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

// ─── Cache Stats ───
export async function getCacheStats(): Promise<{
  total_cached: number;
  memory_cached: number;
}> {
  const { data } = await api.get('/api/cache/stats');
  return data;
}

// ─── Health Check ───
export async function checkHealth(): Promise<HealthResponse> {
  const { data } = await api.get<HealthResponse>('/health');
  return data;
}
