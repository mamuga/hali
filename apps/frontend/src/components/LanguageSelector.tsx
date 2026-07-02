import type { Language } from '../lib/types';

const languages: Array<{ code: Language; label: string }> = [
  { code: 'sw', label: 'Kiswahili' },
  { code: 'so', label: 'Somali' },
  { code: 'am', label: 'Amharic' },
  { code: 'om', label: 'Afaan Oromo' },
  { code: 'ar', label: 'Arabic' },
  { code: 'en', label: 'English' },
];

export function LanguageSelector({ value, onChange }: { value: Language; onChange: (value: Language) => void }) {
  return <select value={value} onChange={(event) => onChange(event.target.value as Language)}>{languages.map((language) => <option key={language.code} value={language.code}>{language.label}</option>)}</select>;
}
