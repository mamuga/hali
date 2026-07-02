import type { Severity } from '../lib/types';

export function SeverityBadge({ severity }: { severity: Severity }) {
  return <span className={`severity severity-${severity}`}>{severity.toUpperCase()}</span>;
}
