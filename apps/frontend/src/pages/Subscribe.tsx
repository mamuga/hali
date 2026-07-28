import { useState } from 'react';
import { BellRing, Loader2, MapPin } from 'lucide-react';
import { toast } from 'sonner';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { subscribe } from '@/lib/api';
import { useLocation } from '@/hooks/useLocation';
import type { Language, Livelihood } from '@hali/types';

const COUNTRIES: Array<[string, string]> = [
  ['KE', 'Kenya'],
  ['ET', 'Ethiopia'],
  ['SO', 'Somalia'],
  ['UG', 'Uganda'],
  ['DJ', 'Djibouti'],
  ['ER', 'Eritrea'],
  ['SD', 'Sudan'],
  ['SS', 'South Sudan'],
];

const LANGUAGES: Array<[Language, string]> = [
  ['sw', 'Kiswahili'],
  ['so', 'Somali'],
  ['am', 'Amharic'],
  ['om', 'Oromo'],
  ['ar', 'Arabic'],
  ['en', 'English'],
];

const LIVELIHOODS: Array<[Livelihood, string]> = [
  ['farmer', 'Farmer'],
  ['pastoralist', 'Pastoralist'],
  ['fisherfolk', 'Fisherfolk'],
  ['urban', 'Urban'],
];

export function SubscribePage() {
  const { coords, request: requestLocation, loading: locating } = useLocation();
  const [phone, setPhone] = useState('');
  const [language, setLanguage] = useState<Language>('sw');
  const [livelihood, setLivelihood] = useState<Livelihood>('farmer');
  const [iso2, setIso2] = useState('KE');
  const [channel, setChannel] = useState<'sms' | 'whatsapp' | 'both'>('sms');
  const [submitting, setSubmitting] = useState(false);
  const [done, setDone] = useState(false);

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!phone.trim()) {
      toast.error('Enter your phone number');
      return;
    }
    setSubmitting(true);
    try {
      await subscribe({
        phone_number: phone.trim(),
        channel,
        language,
        livelihood,
        preferred_iso2: iso2,
        // Sharing GPS is optional; with it the backend can target by polygon
        // intersection instead of by country.
        lat: coords?.lat ?? null,
        lng: coords?.lng ?? null,
      });
      setDone(true);
      toast.success('Subscribed. You will receive Orange and Red alerts.');
    } catch {
      toast.error('Could not subscribe. Check the number and try again.');
    } finally {
      setSubmitting(false);
    }
  }

  if (done) {
    return (
      <div className="flex h-full flex-col items-center justify-center gap-3 p-6 text-center">
        <BellRing className="h-10 w-10 text-primary" />
        <h1 className="text-lg font-semibold">You are subscribed</h1>
        <p className="max-w-xs text-sm text-muted-foreground">
          You will receive Orange and Red alerts for your area. Reply STOP to any message to cancel.
        </p>
        <Button variant="outline" onClick={() => setDone(false)}>
          Subscribe another number
        </Button>
      </div>
    );
  }

  return (
    <div className="h-full overflow-y-auto p-4 pb-24">
      <header className="mb-4">
        <h1 className="flex items-center gap-2 text-lg font-semibold">
          <BellRing className="h-5 w-5 text-primary" />
          Get alerts on your phone
        </h1>
        <p className="mt-1 text-sm text-muted-foreground">
          Alerts in your language, with steps for your livelihood. No account needed.
        </p>
      </header>

      <form onSubmit={onSubmit} className="space-y-4">
        <div>
          <label htmlFor="phone" className="mb-1 block text-sm font-medium">
            Phone number
          </label>
          <Input
            id="phone"
            type="tel"
            inputMode="tel"
            placeholder="+254700000000"
            value={phone}
            onChange={(e) => setPhone(e.target.value)}
            autoComplete="tel"
          />
          <p className="mt-1 text-xs text-muted-foreground">Include your country code.</p>
        </div>

        <Field label="Language">
          <Choices options={LANGUAGES} value={language} onChange={setLanguage} />
        </Field>

        <Field label="Livelihood">
          <Choices options={LIVELIHOODS} value={livelihood} onChange={setLivelihood} />
        </Field>

        <Field label="Country">
          <Choices options={COUNTRIES} value={iso2} onChange={setIso2} />
        </Field>

        <Field label="Channel">
          <Choices
            options={[
              ['sms', 'SMS'],
              ['whatsapp', 'WhatsApp'],
              ['both', 'Both'],
            ]}
            value={channel}
            onChange={setChannel}
          />
        </Field>

        <div className="rounded-lg border border-border p-3">
          <div className="flex items-center justify-between gap-2">
            <div>
              <p className="text-sm font-medium">Share precise location</p>
              <p className="text-xs text-muted-foreground">
                {coords
                  ? `Using ${coords.lat.toFixed(3)}, ${coords.lng.toFixed(3)}`
                  : 'Optional — lets us alert you only when your exact area is affected.'}
              </p>
            </div>
            <Button type="button" variant="outline" size="sm" onClick={requestLocation} disabled={locating}>
              {locating ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <MapPin className="h-3.5 w-3.5" />}
            </Button>
          </div>
        </div>

        <Button type="submit" className="w-full" disabled={submitting}>
          {submitting && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
          Subscribe
        </Button>
      </form>
    </div>
  );
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div>
      <span className="mb-1 block text-sm font-medium">{label}</span>
      {children}
    </div>
  );
}

function Choices<T extends string>({
  options,
  value,
  onChange,
}: {
  options: Array<[T, string]>;
  value: T;
  onChange: (v: T) => void;
}) {
  return (
    <div className="flex flex-wrap gap-1.5">
      {options.map(([key, label]) => (
        <button
          key={key}
          type="button"
          onClick={() => onChange(key)}
          aria-pressed={value === key}
          className={`rounded-full border px-3 py-1.5 text-xs font-medium transition-colors ${
            value === key
              ? 'border-primary bg-primary text-primary-foreground'
              : 'border-border text-muted-foreground hover:bg-muted'
          }`}
        >
          {label}
        </button>
      ))}
    </div>
  );
}
