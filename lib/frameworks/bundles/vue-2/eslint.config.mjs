import tsParser from '@typescript-eslint/parser';
import globals from 'globals';
import vue from 'eslint-plugin-vue';
export default [{ ignores: ['node_modules/**', 'dist/**', '.nuxt/**'] }, ...vue.configs['flat/vue2-recommended'], { files: ['**/*.vue'], languageOptions: { parserOptions: { parser: tsParser, extraFileExtensions: ['.vue'] }, globals: globals.browser } }];
