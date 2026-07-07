/**
 * Centralised environment config.
 * VITE_ prefix required for Vite to expose vars to the browser.
 * Defaults to localhost for local dev.
 */
export const env = {
  apiUrl: (import.meta.env.VITE_API_URL as string) || 'http://localhost:8000',
  environment: (import.meta.env.VITE_ENVIRONMENT as string) || 'development',
} as const;
