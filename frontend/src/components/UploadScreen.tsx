import { useState, useCallback, useRef } from 'react';
import {
  Upload,
  FileText,
  FileCode,
  Film,
  Loader2,
  AlertCircle,
} from 'lucide-react';

interface UploadScreenProps {
  onUpload: (file: File) => Promise<void>;
  isUploading: boolean;
  error: string | null;
}

export default function UploadScreen({
  onUpload,
  isUploading,
  error,
}: UploadScreenProps) {
  const [isDragging, setIsDragging] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const handleDragOver = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(true);
  }, []);

  const handleDragLeave = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(false);
  }, []);

  const handleDrop = useCallback(
    (e: React.DragEvent) => {
      e.preventDefault();
      setIsDragging(false);
      const file = e.dataTransfer.files[0];
      if (file) onUpload(file);
    },
    [onUpload]
  );

  const handleFileSelect = useCallback(
    (e: React.ChangeEvent<HTMLInputElement>) => {
      const file = e.target.files?.[0];
      if (file) onUpload(file);
    },
    [onUpload]
  );

  const formats = [
    { ext: 'JSON', icon: FileCode, color: 'bg-blue-100 text-blue-700' },
    { ext: 'TXT', icon: FileText, color: 'bg-green-100 text-green-700' },
    { ext: 'SRT', icon: Film, color: 'bg-purple-100 text-purple-700' },
    { ext: 'VTT', icon: Film, color: 'bg-orange-100 text-orange-700' },
  ];

  return (
    <div className="min-h-screen bg-gradient-to-br from-slate-50 via-blue-50 to-purple-50 flex items-center justify-center p-8">
      <div className="w-full max-w-lg">
        {/* Header */}
        <div className="text-center mb-8">
          <div className="w-16 h-16 rounded-2xl bg-gradient-to-br from-blue-500 to-purple-600 flex items-center justify-center mx-auto mb-4 shadow-lg">
            <FileText className="w-8 h-8 text-white" />
          </div>
          <h1 className="text-3xl font-bold text-gray-900 mb-2">
            مدقق النصوص العربية
          </h1>
          <p className="text-gray-500 text-sm">
            ارفع ملفاً نصياً وسنقوم بتصحيح الأخطاء الإملائية بالذكاء الاصطناعي
          </p>
        </div>

        {/* Upload Zone */}
        <div
          onDragOver={handleDragOver}
          onDragLeave={handleDragLeave}
          onDrop={handleDrop}
          onClick={() => fileInputRef.current?.click()}
          className={`
            relative cursor-pointer rounded-2xl border-2 border-dashed p-12 text-center transition-all duration-200
            ${
              isDragging
                ? 'border-blue-500 bg-blue-50/50 scale-[1.02]'
                : 'border-gray-300 bg-white hover:border-blue-400 hover:bg-blue-50/30'
            }
            ${isUploading ? 'pointer-events-none opacity-60' : ''}
            shadow-sm hover:shadow-md
          `}
        >
          <input
            ref={fileInputRef}
            type="file"
            accept=".json,.txt,.srt,.vtt"
            onChange={handleFileSelect}
            className="hidden"
          />

          {isUploading ? (
            <div className="flex flex-col items-center gap-4">
              <Loader2 className="w-12 h-12 text-blue-500 animate-spin" />
              <div>
                <p className="text-lg font-semibold text-gray-700">
                  جاري التحليل...
                </p>
                <p className="text-sm text-gray-400 mt-1">
                  نقوم بقراءة الملف وتحضيره للتصحيح
                </p>
              </div>
            </div>
          ) : (
            <>
              <Upload className="w-12 h-12 text-gray-300 mx-auto mb-4" />
              <h3 className="text-lg font-semibold text-gray-700 mb-2">
                اسحب الملف هنا أو انقر للرفع
              </h3>
              <p className="text-sm text-gray-400 mb-6">
                يدعم جميع الصيغ النصية والتوثيقية
              </p>

              {/* Supported Formats */}
              <div className="flex flex-wrap justify-center gap-2">
                {formats.map((f) => (
                  <span
                    key={f.ext}
                    className={`inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-medium ${f.color}`}
                  >
                    <f.icon className="w-3 h-3" />
                    {f.ext}
                  </span>
                ))}
              </div>
            </>
          )}
        </div>

        {/* Error */}
        {error && (
          <div className="mt-4 flex items-center gap-2 px-4 py-3 rounded-xl bg-red-50 border border-red-200 text-red-700 text-sm">
            <AlertCircle className="w-4 h-4 shrink-0" />
            {error}
          </div>
        )}

        {/* Footer */}
        <p className="text-center text-xs text-gray-400 mt-8">
          Spell Corrector v2.0 — Powered by OpenAI + FastAPI
        </p>
      </div>
    </div>
  );
}
