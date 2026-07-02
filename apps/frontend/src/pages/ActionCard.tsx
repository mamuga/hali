import { useState } from 'react';
import { fetchActionCard } from '../lib/api';
import type { ActionCard as ActionCardType, Language, Livelihood } from '../lib/types';

export function ActionCard() {
  const params = new URLSearchParams(location.search);
  const [alertId, setAlertId] = useState(params.get('alert') || '');
  const [livelihood, setLivelihood] = useState<Livelihood>('farmer');
  const [lang, setLang] = useState<Language>('en');
  const [card, setCard] = useState<ActionCardType | null>(null);
  const [error, setError] = useState('');
  async function load() { try { setError(''); setCard(await fetchActionCard(alertId, livelihood, lang)); } catch { setError('No action card found for that alert.'); } }
  return <main className="page"><header className="page-header"><h1>Action Steps</h1></header><section className="form-grid"><input value={alertId} onChange={(e) => setAlertId(e.target.value)} placeholder="Alert ID" /><select value={livelihood} onChange={(e) => setLivelihood(e.target.value as Livelihood)}><option value="farmer">Farmer</option><option value="pastoralist">Pastoralist</option><option value="fisherfolk">Fisherfolk</option><option value="urban">Urban</option></select><select value={lang} onChange={(e) => setLang(e.target.value as Language)}><option value="en">English</option><option value="sw">Kiswahili</option><option value="so">Somali</option><option value="am">Amharic</option><option value="om">Afaan Oromo</option><option value="ar">Arabic</option></select><button onClick={load}>Fetch</button></section>{error && <div className="notice">{error}</div>}{card && <article className="action-card"><h2>{card.livelihood}</h2><pre>{card.steps}</pre></article>}</main>;
}
