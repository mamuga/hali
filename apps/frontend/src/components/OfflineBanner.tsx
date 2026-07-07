import { WifiOff } from 'lucide-react';
import { cn } from '@/lib/utils';

export function OfflineBanner({ show, className }: { show: boolean; className?: string }) {
  if (!show) return null;
  return (
    <div
      role="alert"
      aria-live="polite"
      className={cn(
        'flex items-center gap-2 border-b border-amber-200 bg-amber-50 px-4 py-2.5 text-xs font-medium text-amber-900 dark:border-amber-800 dark:bg-amber-950/40 dark:text-amber-300',
        className,
      )}
    >
      <WifiOff className="h-3.5 w-3.5 shrink-0" />
      <span>Offline - showing cached data. Reports saved for when you reconnect.</span>
    </div>
  );
}
