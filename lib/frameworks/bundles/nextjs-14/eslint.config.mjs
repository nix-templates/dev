import tsParser from '@typescript-eslint/parser';
import globals from 'globals';
import react from 'eslint-plugin-react';
import hooks from 'eslint-plugin-react-hooks';
import next from '@next/eslint-plugin-next';
export default [{ ignores: ['node_modules/**', '.next/**', 'dist/**', 'build/**'] }, {
  files: ['**/*.{js,jsx,ts,tsx,mjs,cjs}'],
  languageOptions: { parser: tsParser, parserOptions: { ecmaFeatures: { jsx: true } }, globals: { ...globals.browser, ...globals.node } },
  settings: { react: { version: '18.0' } },
  plugins: { react, 'react-hooks': hooks, '@next/next': next },
  rules: { ...react.configs.recommended.rules, ...hooks.configs.recommended.rules, 'react/react-in-jsx-scope': 'off', ...next.configs.recommended.rules, ...next.configs['core-web-vitals'].rules },
}];
