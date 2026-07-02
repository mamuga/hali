import { FormEvent, useState } from 'react';
import { useLocation } from '../hooks/useLocation';
import { useReportQueue } from '../hooks/useReportQueue';
import { submitReport } from '../lib/api';
import { addQueuedReport } from '../lib/offlineQueue';
import type { HazardType } from '../lib/types';

export function ReportForm() {
  const { position, locate } = useLocation();
  const { online, queued } = useReportQueue();
  const [hazard, setHazard] = useState<HazardType>('flood');
  const [description, setDescription] = useState('');
  const [message, setMessage] = useState('');
  async function submit(event: FormEvent) { event.preventDefault(); const report = { lat: position?.lat || 0, lng: position?.lng || 0, hazard_type: hazard, description }; try { if (!online) throw new Error('offline'); await submitReport(report); setMessage('Report sent.'); setDescription(''); } catch { addQueuedReport(report); setMessage('Report queued for retry.'); } }
  return <main className="page"><header className="page-header"><h1>Community Report</h1><p>{queued} queued report(s)</p></header><form className="form-grid" onSubmit={submit}><button type="button" onClick={locate}>Use my location</button><input value={position ? `${position.lat.toFixed(4)}, ${position.lng.toFixed(4)}` : ''} readOnly placeholder="Location" /><select value={hazard} onChange={(e) => setHazard(e.target.value as HazardType)}><option value="flood">Flood</option><option value="drought">Drought</option><option value="locust">Locust</option><option value="cyclone">Cyclone</option><option value="health">Health</option><option value="other">Other</option></select><textarea value={description} onChange={(e) => setDescription(e.target.value)} minLength={3} placeholder="What is happening?" /><button type="submit">Submit report</button></form>{message && <div className="notice">{message}</div>}</main>;
}
