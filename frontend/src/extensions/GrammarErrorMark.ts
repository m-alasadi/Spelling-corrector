import { Mark, mergeAttributes } from '@tiptap/core';

/**
 * GrammarErrorMark — Custom Tiptap Mark for grammar/style errors
 * Renders blue double underline decoration
 *
 * Attributes:
 *  - suggestion: the suggested correction text
 *  - errorType: 'grammar' | 'style' | 'punctuation'
 */
export interface GrammarErrorOptions {
  HTMLAttributes: Record<string, any>;
}

declare module '@tiptap/core' {
  interface Commands<ReturnType> {
    grammarError: {
      setGrammarError: (attributes: { suggestion: string; errorType?: string }) => ReturnType;
      toggleGrammarError: (attributes: { suggestion: string; errorType?: string }) => ReturnType;
      unsetGrammarError: () => ReturnType;
    };
  }
}

export const GrammarErrorMark = Mark.create<GrammarErrorOptions>({
  name: 'grammarError',

  addOptions() {
    return {
      HTMLAttributes: {},
    };
  },

  addAttributes() {
    return {
      suggestion: {
        default: null,
        parseHTML: (element) => element.getAttribute('data-suggestion'),
        renderHTML: (attributes) => {
          if (!attributes.suggestion) return {};
          return { 'data-suggestion': attributes.suggestion };
        },
      },
      errorType: {
        default: 'grammar',
        parseHTML: (element) => element.getAttribute('data-error-type') || 'grammar',
        renderHTML: (attributes) => {
          return { 'data-error-type': attributes.errorType || 'grammar' };
        },
      },
    };
  },

  parseHTML() {
    return [
      {
        tag: 'span[data-grammar-error]',
      },
    ];
  },

  renderHTML({ HTMLAttributes }) {
    return [
      'span',
      mergeAttributes(this.options.HTMLAttributes, HTMLAttributes, {
        'data-grammar-error': 'true',
        class: 'grammar-error',
      }),
      0,
    ];
  },

  addCommands() {
    return {
      setGrammarError:
        (attributes) =>
        ({ commands }) => {
          return commands.setMark(this.name, attributes);
        },
      toggleGrammarError:
        (attributes) =>
        ({ commands }) => {
          return commands.toggleMark(this.name, attributes);
        },
      unsetGrammarError:
        () =>
        ({ commands }) => {
          return commands.unsetMark(this.name);
        },
    };
  },
});
