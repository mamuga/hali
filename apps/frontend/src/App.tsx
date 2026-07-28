import { lazy, Suspense } from 'react';
import { BrowserRouter, Route, Routes } from 'react-router-dom';
import { Toaster } from 'sonner';
import { BottomNav } from '@/components/BottomNav';
import { Skeleton } from '@/components/ui/skeleton';
import { useReportQueue } from '@/hooks/useReportQueue';
import { ThemeProvider, useTheme } from '@/lib/theme';
import 'leaflet/dist/leaflet.css';

const AlertFeed = lazy(() => import('@/pages/AlertFeed').then((m) => ({ default: m.AlertFeed })));
const MapView = lazy(() => import('@/pages/MapView').then((m) => ({ default: m.MapView })));
const ActionCardPage = lazy(() => import('@/pages/ActionCard').then((m) => ({ default: m.ActionCardPage })));
const ReportForm = lazy(() => import('@/pages/ReportForm').then((m) => ({ default: m.ReportForm })));
const OfflinePage = lazy(() => import('@/pages/Offline').then((m) => ({ default: m.OfflinePage })));
const SubscribePage = lazy(() => import('@/pages/Subscribe').then((m) => ({ default: m.SubscribePage })));

function PageFallback() {
  return (
    <div className="space-y-3 p-4">
      {Array.from({ length: 4 }).map((_, i) => (
        <Skeleton key={i} className="h-24 w-full" />
      ))}
    </div>
  );
}

function AppShell() {
  const { resolvedTheme } = useTheme();
  // Drains reports queued while offline. Without this mounted somewhere, queued
  // reports were written to localStorage and never sent.
  useReportQueue();

  return (
    <BrowserRouter>
      <div className="flex h-full flex-col bg-background text-foreground">
        <main className="relative flex-1 overflow-hidden">
          <Suspense fallback={<PageFallback />}>
            <Routes>
              <Route path="/" element={<AlertFeed />} />
              <Route path="/map" element={<MapView />} />
              <Route path="/actions" element={<ActionCardPage />} />
              <Route path="/report" element={<ReportForm />} />
              <Route path="/subscribe" element={<SubscribePage />} />
              <Route path="/offline" element={<OfflinePage />} />
            </Routes>
          </Suspense>
        </main>
        <BottomNav />
      </div>
      <Toaster position="top-center" richColors closeButton theme={resolvedTheme} toastOptions={{ duration: 4000 }} />
    </BrowserRouter>
  );
}

export function App() {
  return (
    <ThemeProvider>
      <AppShell />
    </ThemeProvider>
  );
}

export default App;
