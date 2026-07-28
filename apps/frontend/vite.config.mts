import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import tailwindcss from '@tailwindcss/vite';
import { VitePWA } from 'vite-plugin-pwa';

const __dirname = path.dirname(fileURLToPath(import.meta.url));

export default defineConfig({
  root: __dirname,
  cacheDir: '../../node_modules/.vite/apps/frontend',

  plugins: [
    react(),
    tailwindcss(),
    VitePWA({
      registerType: 'autoUpdate',
      includeAssets: ['favicon.ico', 'apple-touch-icon.png'],
      manifest: {
        name: 'HALI - Early Warning',
        short_name: 'HALI',
        description: 'Hyper-local early warning for East Africa',
        theme_color: '#0ea5e9',
        background_color: '#f8fafc',
        display: 'standalone',
        start_url: '/',
        icons: [
          { src: 'pwa-192x192.png', sizes: '192x192', type: 'image/png' },
          { src: 'pwa-512x512.png', sizes: '512x512', type: 'image/png', purpose: 'any maskable' },
        ],
      },
      workbox: {
        navigateFallback: '/index.html',
        navigateFallbackDenylist: [/^\/api/],
        // Order matters: Workbox uses the first matching route. The more
        // specific /api/alerts/* patterns must precede the alert-feed pattern,
        // which would otherwise swallow /api/alerts/geojson?... into the wrong
        // cache because that URL also ends in a query string.
        runtimeCaching: [
          {
            urlPattern: /\/api\/alerts\/geojson/,
            handler: 'StaleWhileRevalidate',
            options: {
              cacheName: 'hali-geojson',
              expiration: { maxEntries: 10, maxAgeSeconds: 300 },
            },
          },
          {
            urlPattern: /\/api\/alerts\/.+\/action-card/,
            handler: 'CacheFirst',
            options: {
              cacheName: 'hali-action-cards',
              expiration: { maxEntries: 100, maxAgeSeconds: 86400 },
            },
          },
          {
            urlPattern: /\/api\/alerts(\?.*)?$/,
            handler: 'StaleWhileRevalidate',
            options: {
              cacheName: 'hali-alerts',
              expiration: { maxEntries: 30, maxAgeSeconds: 300 },
            },
          },
          {
            urlPattern: /\/api\/spatial\//,
            handler: 'StaleWhileRevalidate',
            options: {
              cacheName: 'hali-spatial',
              expiration: { maxEntries: 30, maxAgeSeconds: 300 },
            },
          },
          {
            // ICPAC's WMS tiles are large; cache them like basemap tiles so
            // toggling a layer back on is instant and works offline.
            urlPattern: /^https:\/\/geoportal\.icpac\.net\/geoserver\//,
            handler: 'CacheFirst',
            options: {
              cacheName: 'icpac-wms',
              expiration: { maxEntries: 300, maxAgeSeconds: 604800 },
              cacheableResponse: { statuses: [0, 200] },
            },
          },
          {
            urlPattern: /^https:\/\/[a-c]\.tile\.openstreetmap\.org\//,
            handler: 'CacheFirst',
            options: {
              cacheName: 'osm-tiles',
              expiration: { maxEntries: 1000, maxAgeSeconds: 604800 },
              cacheableResponse: { statuses: [0, 200] },
            },
          },
        ],
      },
    }),
  ],

  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src'),
      '@hali/types': path.resolve(__dirname, '../../packages/types/src/index.ts'),
    },
  },

  server: { port: 5173, host: '0.0.0.0' },
  preview: { port: 4173, host: '0.0.0.0' },

  build: {
    outDir: '../../dist/apps/frontend',
    emptyOutDir: true,
    reportCompressedSize: true,
    commonjsOptions: { transformMixedEsModules: true },
    rollupOptions: {
      output: {
        manualChunks(id) {
          if (id.includes('node_modules/leaflet/') || id.includes('node_modules/react-leaflet')) return 'leaflet';
          if (id.includes('node_modules/react-router-dom') || id.includes('node_modules/react-router')) return 'router';
          if (id.includes('node_modules/@radix-ui')) return 'shadcn';
          if (id.includes('node_modules/react') || id.includes('node_modules/sonner')) return 'vendor';
        },
      },
    },
  },

  test: {
    watch: false,
    globals: true,
    environment: 'jsdom',
    setupFiles: ['src/test-setup.ts'],
    include: ['src/**/*.{test,spec}.{js,mjs,cjs,ts,mts,cts,jsx,tsx}'],
    reporters: ['default'],
    coverage: { reportsDirectory: '../../coverage/apps/frontend', provider: 'v8' },
  },
});
