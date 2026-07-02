import { Link } from 'react-router-dom';
import type { Alert } from '../lib/types';
import { SeverityBadge } from './SeverityBadge';

export function AlertCard({ alert }: { alert: Alert }) {
  return <article className="alert-card"><div className="alert-card__top"><SeverityBadge severity={alert.severity} /><span>{alert.hazard_type}</span></div><h2>{alert.headline || alert.hazard_type}</h2><p>{alert.body || 'No translated alert body is available yet.'}</p><div className="meta">{alert.affected_countries.join(', ') || 'East Africa'}</div><Link to={`/actions?alert=${alert.id}`}>Action steps</Link></article>;
}
