import { registerHooks } from 'node:module';
import { readFileSync, existsSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import ts from 'typescript';
import React from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import assert from 'node:assert/strict';
registerHooks({
  resolve(specifier, context, next) {
    if (specifier.startsWith('.') && context.parentURL?.includes('/src/')) {
      for (const suffix of ['.ts', '.tsx', '/index.ts']) {
        const url = new URL(specifier + suffix, context.parentURL);
        if (existsSync(fileURLToPath(url))) return next(url.href, context);
      }
    }
    return next(specifier, context);
  },
  load(url, context, next) {
    if (/\/src\/.*\.tsx?$/.test(url)) {
      const source = ts.transpileModule(readFileSync(fileURLToPath(url), 'utf8'), {
        compilerOptions: { module: ts.ModuleKind.ESNext, jsx: ts.JsxEmit.ReactJSX, target: ts.ScriptTarget.ES2023 },
      }).outputText;
      return { format: 'module', source, shortCircuit: true };
    }
    return next(url, context);
  },
});
const { FeedbackFollowup } = await import('../src/components/FeedbackFollowup.tsx');
const render = (status: string, isSolved: boolean) => renderToStaticMarkup(React.createElement(FeedbackFollowup, {
  status, isSolved, environmentId: 'puzzle_hints', onSubmitFeedback: async () => {},
  onRevealSolution: async () => {}, onNext: async () => {}, loading: false, hasNext: true,
}));
const unsolved = render('completed', false);
assert.ok(!unsolved.includes('順利完成'), 'ending an unsolved trial must not claim success');
assert.ok(unsolved.includes('尚未解出'), 'explain unsolved outcome');
assert.ok(render('completed', true).includes('已解出'));
assert.ok(!render('aborted', false).includes('>看解法<'), 'aborted trials cannot use the reveal endpoint');
console.log('Feedback rendering regression checks passed');
