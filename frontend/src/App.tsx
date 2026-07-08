import { TextProvider, useTextContext } from './context/TextContext';
import UploadScreen from './components/UploadScreen';
import Stepper from './components/Stepper';
import SpellCheckEditor from './components/SpellCheckEditor';
import GrammarEditor from './components/GrammarEditor';
import GrammarSettingsPanel from './components/GrammarSettingsPanel';
import { Download, ArrowRight, CheckCheck } from 'lucide-react';
import { useCallback, useState } from 'react';
import * as api from './services/api';

function AppContent() {
  const {
    currentStep,
    setCurrentStep,
    jobId,
    segments,
    filename,
    canProceedToGrammar,
    spellErrorCount,
    sseAbortRef,
    setJobId,
    setSegments,
    setFilename,
    setCleanText,
    setIsStreaming,
    setStreamProgress,
    setSpellErrors,
  } = useTextContext();

  const [screen, setScreen] = useState<'upload' | 'editor'>('upload');
  const [uploadError, setUploadError] = useState<string | null>(null);
  const [isUploading, setIsUploading] = useState(false);

  // ── Handle Upload ──
  const handleUpload = useCallback(
    async (file: File) => {
      setIsUploading(true);
      setUploadError(null);

      try {
        const result = await api.uploadFile(file);
        setJobId(result.job_id);
        setFilename(result.filename);
        setSegments([]);
        setIsStreaming(true);
        setStreamProgress(0);
        setScreen('editor');
      } catch (err: any) {
        const message =
          err.response?.data?.detail || err.message || 'حدث خطأ غير متوقع';
        setUploadError(message);
      } finally {
        setIsUploading(false);
      }
    },
    [setJobId, setFilename, setSegments, setIsStreaming, setStreamProgress]
  );

  // ── Handle Back ──
  const handleBack = useCallback(() => {
    if (sseAbortRef.current) {
      sseAbortRef.current();
      sseAbortRef.current = null;
    }
    setScreen('upload');
    setJobId(null);
    setSegments([]);
    setCleanText('');
    setSpellErrors([]);
    setIsStreaming(false);
    setStreamProgress(0);
  }, [sseAbortRef, setJobId, setSegments, setCleanText, setSpellErrors, setIsStreaming, setStreamProgress]);

  // ── Handle Download ──
  const handleDownload = useCallback(() => {
    if (!jobId) return;
    window.open(api.getDownloadUrl(jobId), '_blank');
  }, [jobId]);

  // ── Handle Proceed to Grammar ──
  const handleProceedToGrammar = useCallback(() => {
    if (canProceedToGrammar) {
      setCurrentStep('grammar');
    }
  }, [canProceedToGrammar, setCurrentStep]);

  // ── Upload Screen ──
  if (screen === 'upload') {
    return (
      <UploadScreen
        onUpload={handleUpload}
        isUploading={isUploading}
        error={uploadError}
      />
    );
  }

  // ── Editor Screen ──
  return (
    <div className="min-h-screen flex flex-col bg-gray-50" dir="rtl">
      {/* Top Bar */}
      <div className="bg-white border-b border-gray-200 px-6 py-2.5 flex items-center justify-between">
        <div className="flex items-center gap-3">
          <button
            onClick={handleBack}
            className="flex items-center gap-1.5 px-3 py-1.5 text-sm text-gray-600 hover:text-gray-800 hover:bg-gray-100 rounded-lg transition-all"
          >
            <ArrowRight className="w-4 h-4" />
            رجوع
          </button>
          <span className="text-sm font-medium text-gray-700">📄 {filename}</span>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={handleDownload}
            className="flex items-center gap-1.5 px-3 py-1.5 text-sm text-gray-600 hover:text-gray-800 hover:bg-gray-100 rounded-lg transition-all"
          >
            <Download className="w-4 h-4" />
            تحميل
          </button>
        </div>
      </div>

      {/* Stepper */}
      <Stepper />

      {/* Main Content */}
      <div className="flex-1 flex overflow-hidden">
        {/* Spell Check Step */}
        {currentStep === 'spell' && (
          <>
            <SpellCheckEditor />
            {/* Sidebar: Spell Summary + Next Button */}
            <div className="w-72 bg-white border-l border-gray-200 overflow-y-auto">
              <div className="p-4 space-y-4">
                {/* Spell Stats */}
                <div className="bg-gray-50 rounded-xl p-4">
                  <h4 className="text-sm font-bold text-gray-700 mb-3">
                    ملخص التدقيق الإملائي
                  </h4>
                  <div className="space-y-2">
                    <div className="flex items-center justify-between">
                      <span className="text-xs text-gray-500">المقاطع</span>
                      <span className="text-xs font-semibold text-gray-700">
                        {segments.length}
                      </span>
                    </div>
                    <div className="flex items-center justify-between">
                      <span className="text-xs text-gray-500">الأخطاء</span>
                      <span className="text-xs font-semibold text-red-600">
                        {spellErrorCount}
                      </span>
                    </div>
                  </div>
                </div>

                {/* Accept All Button */}
                {spellErrorCount > 0 && (
                  <button
                    onClick={() => {
                      // Trigger accept all via a custom event
                      const event = new CustomEvent('spell-accept-all');
                      window.dispatchEvent(event);
                    }}
                    className="w-full flex items-center justify-center gap-2 px-4 py-2.5 rounded-xl bg-gradient-to-r from-green-500 to-emerald-600 text-white text-sm font-bold shadow-lg shadow-green-200 hover:shadow-green-300 transition-all"
                  >
                    <CheckCheck className="w-4 h-4" />
                    قبول جميع التصحيحات
                  </button>
                )}

                {/* Navigation to Grammar */}
                <button
                  onClick={handleProceedToGrammar}
                  disabled={!canProceedToGrammar}
                  className={
                    canProceedToGrammar
                      ? 'w-full flex items-center justify-center gap-2 px-4 py-3 rounded-xl bg-gradient-to-r from-indigo-500 to-purple-600 text-white text-sm font-bold shadow-lg shadow-indigo-200 hover:shadow-indigo-300 transition-all'
                      : 'w-full flex items-center justify-center gap-2 px-4 py-3 rounded-xl bg-gray-100 text-gray-400 text-sm font-bold cursor-not-allowed'
                  }
                >
                  <ArrowRight className="w-4 h-4" />
                  التالي: الصياغة والنحو
                </button>
              </div>
            </div>
          </>
        )}

        {/* Grammar Step */}
        {currentStep === 'grammar' && (
          <>
            <GrammarEditor />
            <GrammarSettingsPanel />
          </>
        )}
      </div>
    </div>
  );
}

export default function App() {
  return (
    <TextProvider>
      <AppContent />
    </TextProvider>
  );
}
