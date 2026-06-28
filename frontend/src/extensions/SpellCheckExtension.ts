import { Extension } from '@tiptap/core';
import { Plugin, PluginKey } from '@tiptap/pm/state';
import { Decoration, DecorationSet } from '@tiptap/pm/view';
import type { WordDiff } from '../types';

export interface SpellCheckOptions {
  wordDiffs: WordDiff[];
  onWordClick: (wordIndex: number) => void;
}

export const SpellCheckKey = new PluginKey('spellCheck');

function buildDecorations(
  wordDiffs: WordDiff[],
  onWordClick: (wordIndex: number) => void
): DecorationSet {
  const decorations: Decoration[] = [];
  let charPos = 0;
  let wordIdx = 0;

  for (const token of wordDiffs) {
    const tokenLen = token.value.length;

    if (token.type === 'word') {
      if (token.is_error && !token.accepted && !token.ignored) {
        // ─── Error word: red wavy underline ───
        decorations.push(
          Decoration.inline(charPos, charPos + tokenLen, {
            class:
              'spell-error relative cursor-pointer underline decoration-red-500 decoration-wavy underline-offset-4 decoration-[1.5px] rounded-sm px-[1px] hover:bg-red-50 transition-colors',
            'data-word-index': String(wordIdx),
            'data-suggestion': token.suggestion || '',
            'data-original': token.value,
          } as any)
        );
      } else if (token.accepted) {
        // ─── Accepted word: green highlight ───
        decorations.push(
          Decoration.inline(charPos, charPos + tokenLen, {
            class:
              'bg-green-100 text-green-800 rounded-sm px-[1px] font-medium',
          } as any)
        );
      } else if (token.ignored) {
        // ─── Ignored word: subtle style ───
        decorations.push(
          Decoration.inline(charPos, charPos + tokenLen, {
            class: 'text-gray-400',
          } as any)
        );
      }
      wordIdx++;
    }

    charPos += tokenLen;
  }

  return DecorationSet.create(/* doc */ undefined as any, decorations);
}

export const SpellCheckExtension = Extension.create<SpellCheckOptions>({
  name: 'spellCheck',

  addOptions() {
    return {
      wordDiffs: [],
      onWordClick: () => {},
    };
  },

  addProseMirrorPlugins() {
    const { wordDiffs, onWordClick } = this.options;

    return [
      new Plugin({
        key: SpellCheckKey,
        state: {
          init: () => DecorationSet.empty,
          apply: (_tr, _old, _oldState, _newState) => {
            // Rebuild decorations when wordDiffs change
            if (wordDiffs.length > 0) {
              return buildDecorations(wordDiffs, onWordClick);
            }
            return DecorationSet.empty;
          },
        },
        props: {
          decorations(state) {
            return this.getState(state);
          },
          // Handle click on error words
          handleClick(view, pos) {
            // Find which word was clicked
            const decorations = this.getState(view.state);
            if (!decorations) return false;

            let found = false;
            decorations.find(pos, pos, (spec) => {
              const wordIndex = spec['data-word-index'];
              if (wordIndex !== undefined) {
                onWordClick(parseInt(wordIndex));
                found = true;
              }
              return false;
            });

            return found;
          },
        },
      }),
    ];
  },
});
