/// <reference types="vitest" />
import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

export default defineConfig({
  plugins: [react()],

  // Root-level esbuild JSX configuration.
  //
  // @vitejs/plugin-react normally sets `esbuild.jsx = 'preserve'` via its
  // config hook so that Babel (not esbuild) handles JSX in the dev/build
  // pipeline — and Babel uses the automatic runtime by default.
  //
  // However, vitest@1.x and vite@8.x have an incompatible plugin-bridge:
  // the plugin's config hook does not fire inside the Vitest runner, so
  // esbuild falls back to its built-in default (classic runtime →
  // React.createElement calls) — causing "ReferenceError: React is not
  // defined" across every JSX test file.
  //
  // Setting `jsx: 'automatic'` here at the root provides the correct default:
  //   • In tests (plugin hooks absent): esbuild uses automatic runtime → ✓
  //   • In dev/build (plugin runs): plugin overrides with `jsx: 'preserve'`
  //     and Babel takes over — these two lines are effectively ignored → ✓
  esbuild: {
    jsx: 'automatic',
    jsxImportSource: 'react',
  },

  server: {
    port: 3000,
    proxy: {
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
    },
  },

  test: {
    // Make describe / it / expect / beforeEach available globally (mirrors Jest API).
    globals: true,

    // Browser-like DOM environment — matches what Jest used jsdom for.
    environment: 'jsdom',

    // Runs before every test file: sets up @testing-library/jest-dom matchers.
    setupFiles: ['./src/setupTests.js'],

    // Exclude Playwright e2e specs — those run separately via `npx playwright test`.
    exclude: ['node_modules', 'e2e'],

    // Coverage via v8 (no extra instrumentation pass needed).
    coverage: {
      provider: 'v8',
      reporter: ['text', 'html'],
      exclude: ['src/__mocks__/**', 'src/main.jsx'],
    },
  },
});
