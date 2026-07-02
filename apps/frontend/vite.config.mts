/// <reference types='vitest' />
import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import { nxViteTsPaths } from '@nx/vite/plugins/nx-tsconfig-paths.plugin';
import { VitePWA } from 'vite-plugin-pwa';

export default defineConfig(() => ({
  root: __dirname,
  cacheDir: '../../node_modules/.vite/apps/frontend',
  server: { port: 5173, host: '0.0.0.0' },
  preview: { port: 4173, host: '0.0.0.0' },
  plugins: [
    react(),
    nxViteTsPaths(),
    VitePWA({
      registerType: 'autoUpdate',
      includeAssets: ['favicon.ico'],
      manifest: { name: 'HALI - Early Warning', short_name: 'HALI', theme_color: '#0F6E56', background_color: '#F6F8F5', display: 'standalone', start_url: '/', icons: [{ src: '/favicon.ico', sizes: '64x64 32x32 24x24 16x16', type: 'image/x-icon' }] },
      workbox: {
        navigateFallback: '/offline',
        runtimeCaching: [
          { urlPattern: ({ url }) => url.pathname.startsWith('/api/alerts'), handler: 'StaleWhileRevalidate', options: { cacheName: 'hali-alerts', expiration: { maxAgeSeconds: 300, maxEntries: 60 } } },
          { urlPattern: /^https:\/\/[abc]\.tile\.openstreetmap\.org\/.*$/i, handler: 'CacheFirst', options: { cacheName: 'osm-tiles', expiration: { maxAgeSeconds: 60 * 60 * 24 * 7, maxEntries: 500 } } },
          { urlPattern: ({ url }) => url.pathname.includes('/action-card'), handler: 'StaleWhileRevalidate', options: { cacheName: 'hali-action-cards', expiration: { maxAgeSeconds: 60 * 60 * 24, maxEntries: 100 } } },
        ],
      },
    }),
  ],
  build: { outDir: '../../dist/apps/frontend', emptyOutDir: true, reportCompressedSize: true, commonjsOptions: { transformMixedEsModules: true } },
  test: { watch: false, globals: true, environment: 'jsdom', include: ['src/**/*.{test,spec}.{js,mjs,cjs,ts,mts,cts,jsx,tsx}'], reporters: ['default'], coverage: { reportsDirectory: '../../coverage/apps/frontend', provider: 'v8' } },
}));
