import { useTextContext } from '../context/TextContext';
import { Check, ChevronLeft } from 'lucide-react';
import { clsx } from 'clsx';

export default function Stepper() {
  const { currentStep, setCurrentStep, canProceedToGrammar, spellErrorCount } =
    useTextContext();

  const steps = [
    {
      id: 'spell' as const,
      label: 'التدقيق الإملائي',
      icon: '📝',
      description: 'تصحيح الأخطاء الإملائية والحروف',
    },
    {
      id: 'grammar' as const,
      label: 'الصياغة والنحو',
      icon: '📐',
      description: 'التدقيق النحوي وتحسين الصياغة',
    },
  ];

  return (
    <div className="bg-white border-b border-gray-200 shadow-sm">
      <div className="max-w-5xl mx-auto px-4 py-3">
        <div className="flex items-center justify-center gap-2">
          {steps.map((step, index) => {
            const isActive = currentStep === step.id;
            const isCompleted =
              step.id === 'spell' && canProceedToGrammar && spellErrorCount === 0;
            const isDisabled = step.id === 'grammar' && !canProceedToGrammar;

            return (
              <div key={step.id} className="flex items-center">
                {/* Step Button */}
                <button
                  onClick={() => {
                    if (!isDisabled) setCurrentStep(step.id);
                  }}
                  disabled={isDisabled}
                  className={clsx(
                    'flex items-center gap-2.5 px-5 py-2.5 rounded-xl transition-all duration-200',
                    isActive &&
                      'bg-gradient-to-r from-blue-500 to-indigo-600 text-white shadow-lg shadow-blue-200',
                    !isActive && !isDisabled && 'bg-gray-50 text-gray-600 hover:bg-gray-100',
                    isDisabled && 'bg-gray-50 text-gray-300 cursor-not-allowed',
                    isCompleted && !isActive && 'bg-green-50 text-green-700'
                  )}
                >
                  {/* Step Number / Check */}
                  <span
                    className={clsx(
                      'w-7 h-7 rounded-full flex items-center justify-center text-xs font-bold',
                      isActive && 'bg-white/20 text-white',
                      !isActive && !isCompleted && 'bg-gray-200 text-gray-500',
                      isCompleted && 'bg-green-500 text-white'
                    )}
                  >
                    {isCompleted ? (
                      <Check className="w-4 h-4" />
                    ) : (
                      index + 1
                    )}
                  </span>

                  {/* Icon + Label */}
                  <span className="text-sm">{step.icon}</span>
                  <span className="text-sm font-semibold">{step.label}</span>
                </button>

                {/* Connector Arrow */}
                {index < steps.length - 1 && (
                  <ChevronLeft
                    className={clsx(
                      'w-5 h-5 mx-2',
                      canProceedToGrammar ? 'text-blue-400' : 'text-gray-300'
                    )}
                  />
                )}
              </div>
            );
          })}
        </div>

        {/* Description */}
        <p className="text-center text-xs text-gray-400 mt-2">
          {steps.find((s) => s.id === currentStep)?.description}
        </p>
      </div>
    </div>
  );
}
