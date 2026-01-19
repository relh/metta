import css from '@eslint/css'
import eslint from '@eslint/js'
import { globalIgnores } from 'eslint/config'
import tseslint from 'typescript-eslint'

export default tseslint.config(
  globalIgnores(['dist', '.next', 'next-env.d.ts', 'node_modules']),
  {
    name: 'eslint',
    files: ['**/*.ts'],
    ...eslint.configs.recommended,
  },
  {
    name: 'typescript-eslint',
    files: ['**/*.ts'],
    extends: tseslint.configs.recommended,
  },
  {
    files: ['style.css'],
    plugins: { css },
    language: 'css/css',
    extends: [css.configs.recommended],
  },
  // disable some rules
  {
    rules: {
      '@typescript-eslint/no-explicit-any': 'off',
      '@typescript-eslint/no-unused-vars': 'off',
      'no-prototype-builtins': 'off',
      'css/use-baseline': 'off',
      'css/no-important': 'off',
    },
  }
)
