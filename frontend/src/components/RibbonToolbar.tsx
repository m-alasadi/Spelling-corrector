import { useState } from 'react';
import {
  FileText,
  CheckCircle,
  Eye,
  Download,
  Brain,
  Sparkles,
  Languages,
  AlertCircle,
} from 'lucide-react';

interface RibbonToolbarProps {
  errorCount: number;
  correctedCount: number;
  totalSegments: number;
  isProcessing: boolean;
  onCorrect: () => void;
  onAcceptAll: () => void;
  onIgnoreAll: () => void;
  onDownload: () => void;
  onJumpNext: () => void;
  /** Whether the grammar tab is currently active */
  activeMode: 'spell' | 'grammar';
  /** Callback when user switches between spell/grammar tabs */
  onModeChange: (mode: 'spell' | 'grammar') => void;
  /** Grammar error count */
  grammarErrorCount?: number;
}

type TabId = 'file' | 'home' | 'review' | 'grammar';

export default function RibbonToolbar({
  errorCount,
  correctedCount,
  totalSegments,
  isProcessing,
  onCorrect,
  onAcceptAll,
  onIgnoreAll,
  onDownload,
  onJumpNext,
  activeMode: _activeMode,
  onModeChange,
  grammarErrorCount = 0,
}: RibbonToolbarProps) {
  const [activeTab, setActiveTab] = useState<TabId>('review');

  const tabs: { id: TabId; label: string }[] = [
    { id: 'file', label: 'ملف' },
    { id: 'home', label: 'الشريط الرئيسي' },
    { id: 'review', label: '📝 إملائي' },
    { id: 'grammar', label: '📐 نحوي ✨' },
  ];

  return (
    <div className="bg-white border-b border-gray-200 shadow-sm sticky top-0 z-50">
      {/* ─── Title Bar ─── */}
      <div className="flex items-center justify-between px-4 py-2 border-b border-gray-100">
        <div className="flex items-center gap-3">
          <div className="flex items-center gap-2">
            <div className="w-8 h-8 rounded-lg bg-gradient-to-br from-blue-500 to-purple-600 flex items-center justify-center">
              <Sparkles className="w-4 h-4 text-white" />
            </div>
            <div>
              <h1 className="text-sm font-semibold text-gray-800">
                مدقق النصوص العربية
              </h1>
              <p className="text-[10px] text-gray-400">AI-Powered Spell Checker</p>
            </div>
          </div>
        </div>

        {/* Status Badges */}
        <div className="flex items-center gap-3">
          <div className="flex items-center gap-2 px-3 py-1.5 rounded-full bg-gray-50 border border-gray-200">
            <div
              className={`w-2 h-2 rounded-full ${
                errorCount > 0
                  ? 'bg-red-500 animate-pulse'
                  : 'bg-green-500'
              }`}
            />
            <span className="text-xs font-medium text-gray-600">
              {errorCount} أخطاء
            </span>
          </div>
          <div className="flex items-center gap-2 px-3 py-1.5 rounded-full bg-green-50 border border-green-200">
            <CheckCircle className="w-3.5 h-3.5 text-green-600" />
            <span className="text-xs font-medium text-green-700">
              {correctedCount} تصحيح
            </span>
          </div>
          <div className="text-xs text-gray-400">
            {totalSegments} مقاطع
          </div>
        </div>
      </div>

      {/* ─── Tabs ─── */}
      <div className="flex items-center gap-0 px-4 border-b border-gray-100">
        {tabs.map((tab) => (
          <button
            key={tab.id}
            onClick={() => {
              setActiveTab(tab.id);
              // Sync mode when switching between spell/grammar tabs
              if (tab.id === 'review') onModeChange('spell');
              if (tab.id === 'grammar') onModeChange('grammar');
            }}
            className={`px-4 py-2.5 text-sm font-medium border-b-2 transition-all ${
              activeTab === tab.id
                ? 'border-blue-500 text-blue-600 bg-blue-50/50'
                : 'border-transparent text-gray-500 hover:text-gray-700 hover:bg-gray-50'
            }`}
          >
            {tab.label}
          </button>
        ))}
      </div>

      {/* ─── Ribbon Content ─── */}
      <div className="flex items-center gap-1 px-4 py-2.5 flex-wrap">
        {activeTab === 'review' && (
          <>
            {/* AI Correction Group */}
            <div className="flex items-center gap-1.5 pl-3 border-l border-gray-200">
              <button
                onClick={onCorrect}
                disabled={isProcessing}
                className="flex items-center gap-2 px-4 py-2 rounded-lg bg-gradient-to-r from-blue-500 to-purple-600 text-white text-sm font-semibold hover:from-blue-600 hover:to-purple-700 disabled:opacity-50 disabled:cursor-not-allowed transition-all shadow-sm hover:shadow-md"
              >
                {isProcessing ? (
                  <>
                    <div className="w-4 h-4 border-2 border-white border-t-transparent rounded-full animate-spin" />
                    جاري التصحيح...
                  </>
                ) : (
                  <>
                    <Brain className="w-4 h-4" />
                    تدقيق ذكي (AI)
                  </>
                )}
              </button>
            </div>

            {/* Corrections Group */}
            <div className="flex items-center gap-1.5 px-3 border-l border-gray-200">
              <button
                onClick={onAcceptAll}
                className="flex items-center gap-1.5 px-3 py-2 rounded-lg text-sm font-medium text-green-700 bg-green-50 hover:bg-green-100 border border-green-200 transition-all"
              >
                <CheckCircle className="w-4 h-4" />
                قبول الكل
              </button>
              <button
                onClick={onIgnoreAll}
                className="flex items-center gap-1.5 px-3 py-2 rounded-lg text-sm font-medium text-gray-600 bg-gray-50 hover:bg-gray-100 border border-gray-200 transition-all"
              >
                <Eye className="w-4 h-4" />
                تجاهل الكل
              </button>
            </div>

            {/* Navigation Group */}
            <div className="flex items-center gap-1.5 px-3 border-l border-gray-200">
              <button
                onClick={onJumpNext}
                className="flex items-center gap-1.5 px-3 py-2 rounded-lg text-sm font-medium text-blue-600 bg-blue-50 hover:bg-blue-100 border border-blue-200 transition-all"
              >
                ⬇️ الخطأ التالي
              </button>
            </div>

            {/* Spacer */}
            <div className="flex-1" />

            {/* Download */}
            <div className="flex items-center gap-1.5">
              <button
                onClick={onDownload}
                className="flex items-center gap-1.5 px-3 py-2 rounded-lg text-sm font-medium text-gray-600 bg-gray-50 hover:bg-gray-100 border border-gray-200 transition-all"
              >
                <Download className="w-4 h-4" />
                تحميل
              </button>
            </div>
          </>
        )}

        {activeTab === 'file' && (
          <div className="flex items-center gap-3 px-2">
            <button className="flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium text-gray-700 hover:bg-gray-100 transition-all">
              <FileText className="w-4 h-4" />
              فتح ملف
            </button>
            <button
              onClick={onDownload}
              className="flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium text-gray-700 hover:bg-gray-100 transition-all"
            >
              <Download className="w-4 h-4" />
              حفظ
            </button>
          </div>
        )}

        {activeTab === 'home' && (
          <div className="flex items-center gap-3 px-2 text-sm text-gray-500">
            <span>الشريط الرئيسي</span>
          </div>
        )}

        {activeTab === 'grammar' && (
          <>
            {/* Grammar Mode Info */}
            <div className="flex items-center gap-2 pl-3 border-l border-gray-200">
              <div className="flex items-center gap-2 px-3 py-1.5 rounded-full bg-purple-50 border border-purple-200">
                <Languages className="w-3.5 h-3.5 text-purple-600" />
                <span className="text-xs font-medium text-purple-700">
                  وضع التدقيق النحوي
                </span>
              </div>
            </div>

            {/* Grammar Stats */}
            <div className="flex items-center gap-1.5 px-3 border-l border-gray-200">
              {grammarErrorCount > 0 ? (
                <div className="flex items-center gap-2 px-3 py-1.5 rounded-full bg-orange-50 border border-orange-200">
                  <AlertCircle className="w-3.5 h-3.5 text-orange-600" />
                  <span className="text-xs font-medium text-orange-700">
                    {grammarErrorCount} أخطاء نحوية
                  </span>
                </div>
              ) : (
                <div className="flex items-center gap-2 px-3 py-1.5 rounded-full bg-green-50 border border-green-200">
                  <CheckCircle className="w-3.5 h-3.5 text-green-600" />
                  <span className="text-xs font-medium text-green-700">
                    لا توجد أخطاء نحوية
                  </span>
                </div>
              )}
            </div>

            {/* Spacer */}
            <div className="flex-1" />

            {/* Instructions */}
            <div className="text-xs text-gray-400 px-2">
              حدد نصاً ثم استخدم اللوحة الجانبية للتدقيق النحوي
            </div>
          </>
        )}
      </div>
    </div>
  );
}
