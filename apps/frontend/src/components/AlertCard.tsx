import { ChevronRight } from 'lucide-react';
import { Card, CardContent } from '@/components/ui/card';
import { cn } from '@/lib/utils';
import { hazardIcon } from '@/lib/hazards';
import { SeverityBadge } from './SeverityBadge';
import type { Alert } from '@hali/types';

const SEVERITY_BORDER: Record<string, string> = {
  red: 'border-l-red-500',
  orange: 'border-l-orange-500',
  green: 'border-l-green-600',
};

interface Props {
  alert: Alert;
  onClick?: () => void;
  className?: string;
}

export function AlertCard({ alert, onClick, className }: Props) {
  const Icon = hazardIcon(alert.hazard_type);
  const headline = alert.headline ?? `${alert.hazard_type} alert`;

  return (
    <Card
      className={cn(
        'cursor-pointer border-l-4 transition-all duration-150 hover:-translate-y-0.5 hover:shadow-md active:translate-y-0 active:shadow-sm',
        SEVERITY_BORDER[alert.severity] ?? 'border-l-primary',
        className,
      )}
      onClick={onClick}
      role="button"
      tabIndex={0}
      onKeyDown={(e) => e.key === 'Enter' && onClick?.()}
      aria-label={headline}
    >
      <CardContent className="p-4">
        <div className="flex items-start gap-3">
          <div className="mt-0.5 shrink-0 rounded-lg bg-muted p-2">
            <Icon className="h-4 w-4 text-muted-foreground" strokeWidth={1.5} />
          </div>
          <div className="min-w-0 flex-1">
            <div className="mb-1.5 flex items-start justify-between gap-2">
              <p className="line-clamp-2 text-sm font-semibold leading-snug text-foreground">{headline}</p>
              <SeverityBadge severity={alert.severity} className="mt-0.5 shrink-0" />
            </div>
            {alert.body && (
              <p className="mb-2 line-clamp-2 text-xs leading-relaxed text-muted-foreground">{alert.body}</p>
            )}
            <div className="flex items-center justify-between gap-2">
              <div className="flex min-w-0 items-center gap-3 text-[11px] text-muted-foreground">
                <span className="truncate">{(alert.affected_countries ?? []).join(', ')}</span>
                {alert.valid_to && (
                  <span className="shrink-0">
                    Until {new Date(alert.valid_to).toLocaleDateString('en-GB', { day: 'numeric', month: 'short' })}
                  </span>
                )}
              </div>
              {onClick && <ChevronRight className="h-4 w-4 shrink-0 text-muted-foreground" />}
            </div>
          </div>
        </div>
      </CardContent>
    </Card>
  );
}
