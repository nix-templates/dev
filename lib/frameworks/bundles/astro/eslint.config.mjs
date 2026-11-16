import tsParser from '@typescript-eslint/parser';
import globals from 'globals';
const base = [{ ignores: ['node_modules/**', 'dist/**', 'build/**', '.nuxt/**', '.output/**', '.svelte-kit/**', '.astro/**', '.vitepress/cache/**'] }, {
  files: ['**/*.{js,jsx,ts,tsx,mjs,cjs}'],
  languageOptions: { parser: tsParser, parserOptions: { ecmaFeatures: { jsx: true } }, globals: { ...globals.browser, ...globals.node } },
  rules: { 'no-debugger': 'error', 'no-constant-condition': 'error', 'no-dupe-args': 'error', 'constructor-super': 'error', 'valid-typeof': 'error' },
}];
import astro from 'eslint-plugin-astro';
export default [...base, ...astro.configs['flat/recommended'], { files: ['**/*.astro'], languageOptions: { parserOptions: { parser: tsParser, extraFileExtensions: ['.astro'] } } }];
