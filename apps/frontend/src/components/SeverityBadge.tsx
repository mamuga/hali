import { cn } from '@/lib/utils';
import type { Severity } from '@hali/types';

const config: Record<Severity, { label: string; cls: string }> = {
  red: { label: 'HIGH', cls: 'bg-red-100 text-red-800 dark:bg-red-900/30 dark:text-red-400' },
  orange: { label: 'MEDIUM', cls: 'bg-orange-100 text-orange-800 dark:bg-orange-900/30 dark:text-orange-400' },
  green: { label: 'LOW', cls: 'bg-green-100 text-green-800 dark:bg-green-900/30 dark:text-green-400' },
};

const dots: Record<Severity, string> = {
  red: 'bg-red-500',
  orange: 'bg-orange-500',
  green: 'bg-green-600',
};

export function SeverityBadge({ severity, className }: { severity: Severity; className?: string }) {
  const { label, cls } = config[severity] ?? config.green;
  return (
    <span
      className={cn(
        'inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-[11px] font-semibold tracking-wide',
        cls,
        className,
      )}
    >
      <span className={cn('h-1.5 w-1.5 shrink-0 rounded-full', dots[severity])} />
      {label}
    </span>
  );
}
