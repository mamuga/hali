import { WifiOff } from 'lucide-react';
import { Button } from '@/components/ui/button';

export function OfflinePage() {
  return (
    <div className="flex h-full flex-col items-center justify-center px-6 text-center">
      <div className="mb-6 rounded-full bg-muted p-5">
        <WifiOff className="h-10 w-10 text-muted-foreground" strokeWidth={1.5} />
      </div>
      <h1 className="mb-2 text-xl font-bold">You are offline</h1>
      <p className="mb-8 max-w-xs text-sm text-muted-foreground">
        HALI is showing cached alerts. Some features are unavailable until you reconnect.
      </p>
      <Button onClick={() => window.location.reload()} variant="outline">
        Try reconnecting
      </Button>
    </div>
  );
}
