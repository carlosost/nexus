/**
 * Vitest global test setup.
 *
 * Extends Vitest's `expect` with jest-dom matchers:
 *   toBeInTheDocument(), toHaveTextContent(), toHaveClass(), etc.
 *
 * This file is referenced in vite.config.js → test.setupFiles.
 */
import '@testing-library/jest-dom';
