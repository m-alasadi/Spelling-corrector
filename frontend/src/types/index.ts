// ─── Word Diff Types ───
export interface WordDiff {
  type: 'word' | 'space' | 'punct';
  value: string;
  is_error: boolean;
  suggestion: string | null;
  merged?: boolean;
  accepted?: boolean;
  ignored?: boolean;
}

// ─── Segment Types ───
export interface Segment {
  id: number;
  text_original: string;
  text_corrected: string | null;
  speaker: string | null;
  word_diffs?: WordDiff[];
  error_count?: number;
}

// ─── Job Types ───
export interface JobData {
  job_id: string;
  source_file: string;
  language: string;
  segments: Segment[];
}

export interface UploadResponse {
  success: boolean;
  job_id: string;
  filename: string;
  total_segments: number;
  segments_with_text: number;
  preview: Segment[];
  data: JobData;
}

export interface CorrectResponse {
  success: boolean;
  job_id: string;
  corrected_count: number;
  total_segments: number;
  editor_url: string;
  stats: CorrectionStats;
}

export interface CorrectionStats {
  total_words: number;
  dict_corrections: number;
  ai_corrections: number;
  unknown_words: number;
  cached: number;
  api_calls: number;
}

export interface ApplyResponse {
  success: boolean;
  remaining_errors: number;
  total_errors: number;
}

export interface DictStats {
  total_rules: number;
  total_words: number;
  dict_path: string;
}

export interface HealthResponse {
  status: string;
  timestamp: string;
}
