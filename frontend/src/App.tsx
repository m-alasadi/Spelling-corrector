import { useState, useCallback } from 'react';
import type { JobData } from './types';
import * as api from './services/api';
import UploadScreen from './components/UploadScreen';
import WordEditor from './components/WordEditor';

type AppState =
  | { screen: 'upload' }
  | { screen: 'processing'; jobId: string; filename: string }
  | { screen: 'editor'; jobId: string; data: JobData; filename: string; correctedCount: number };

function App() {
  const [state, setState] = useState<AppState>({ screen: 'upload' });
  const [uploadError, setUploadError] = useState<string | null>(null);
  const [isUploading, setIsUploading] = useState(false);

  const handleUpload = useCallback(async (file: File) => {
    setIsUploading(true);
    setUploadError(null);

    try {
      // Step 1: Upload file
      const uploadResult = await api.uploadFile(file);

      setState({
        screen: 'processing',
        jobId: uploadResult.job_id,
        filename: uploadResult.filename,
      });

      // Step 2: Run correction
      const correctResult = await api.correctFile(uploadResult.job_id);

      // Step 3: Fetch corrected data with word_diffs
      const jobData = await api.getJobData(correctResult.job_id);

      // Step 4: Open editor
      setState({
        screen: 'editor',
        jobId: correctResult.job_id,
        data: jobData.data,
        filename: uploadResult.filename,
        correctedCount: correctResult.corrected_count,
      });
    } catch (err: any) {
      const message =
        err.response?.data?.detail || err.message || 'حدث خطأ غير متوقع';
      setUploadError(message);
      setState({ screen: 'upload' });
    } finally {
      setIsUploading(false);
    }
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

      {state.screen === 'processing' && (
        <div className="min-h-screen bg-gradient-to-br from-slate-50 via-blue-50 to-purple-50 flex items-center justify-center">
          <div className="text-center">
            <div className="w-16 h-16 border-4 border-blue-500 border-t-transparent rounded-full animate-spin mx-auto mb-6" />
            <h2 className="text-xl font-semibold text-gray-700 mb-2">
              جاري التصحيح...
            </h2>
            <p className="text-sm text-gray-400">
              نقوم بتحليل "{state.filename}" باستخدام الذكاء الاصطناعي
            </p>
            <p className="text-xs text-gray-400 mt-4">
              قد يستغرق هذا بعض الوقت حسب حجم الملف
            </p>
          </div>
        </div>
      )}

      {state.screen === 'editor' && (
        <WordEditor
          jobId={state.jobId}
          segments={state.data.segments}
          filename={state.filename}
          initialCorrectedCount={state.correctedCount}
        />
      )}
    </div>
  );
}

export default App;
