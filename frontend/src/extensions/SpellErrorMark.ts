import { Mark, mergeAttributes } from '@tiptap/core';

/**
 * SpellErrorMark — Custom Tiptap Mark for spelling errors
 * Renders red wavy underline decoration
 *
 * Attributes:
 *  - suggestion: the suggested correction text
 *  - wordIndex: index of the word in the segment
 *  - segmentId: the segment this error belongs to
 */
export interface SpellErrorOptions {
  HTMLAttributes: Record<string, any>;
}

declare module '@tiptap/core' {
  interface Commands<ReturnType> {
    spellError: {
      /**
       * Set a spell error mark on the selected text
       */
      setSpellError: (attributes: { suggestion: string; wordIndex: number; segmentId: number }) => ReturnType;
      /**
       * Toggle spell error mark on/off
       */
      toggleSpellError: (attributes: { suggestion: string; wordIndex: number; segmentId: number }) => ReturnType;
      /**
       * Remove spell error mark
       */
      unsetSpellError: () => ReturnType;
    };
  }
}

export const SpellErrorMark = Mark.create<SpellErrorOptions>({
  name: 'spellError',

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
      wordIndex: {
        default: 0,
        parseHTML: (element) => parseInt(element.getAttribute('data-word-index') || '0', 10),
        renderHTML: (attributes) => {
          return { 'data-word-index': String(attributes.wordIndex) };
        },
      },
      segmentId: {
        default: 0,
        parseHTML: (element) => parseInt(element.getAttribute('data-segment-id') || '0', 10),
        renderHTML: (attributes) => {
          return { 'data-segment-id': String(attributes.segmentId) };
        },
      },
    };
  },

  parseHTML() {
    return [
      {
        tag: 'span[data-spell-error]',
      },
    ];
  },

  renderHTML({ HTMLAttributes }) {
    return [
      'span',
      mergeAttributes(this.options.HTMLAttributes, HTMLAttributes, {
        'data-spell-error': 'true',
        class: 'spell-error',
      }),
      0,
    ];
  },

  addCommands() {
    return {
      setSpellError:
        (attributes) =>
        ({ commands }) => {
          return commands.setMark(this.name, attributes);
        },
      toggleSpellError:
        (attributes) =>
        ({ commands }) => {
          return commands.toggleMark(this.name, attributes);
        },
      unsetSpellError:
        () =>
        ({ commands }) => {
          return commands.unsetMark(this.name);
        },
    };
  },
});
