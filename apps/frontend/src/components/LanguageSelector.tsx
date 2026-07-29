import { Languages } from 'lucide-react';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { cn } from '@/lib/utils';
import type { Language } from '@hali/types';

// Labels are written in each language's own script — someone who reads only
// Tigrinya cannot find "Tigrinya" in a list of English names.
const LANGS: { code: Language; label: string; native: string }[] = [
  { code: 'sw', label: 'Kiswahili', native: 'SW' },
  { code: 'so', label: 'Soomaali', native: 'SO' },
  { code: 'am', label: 'አማርኛ', native: 'AM' },
  { code: 'om', label: 'Afaan Oromoo', native: 'OM' },
  { code: 'ar', label: 'العربية', native: 'AR' },
  { code: 'en', label: 'English', native: 'EN' },
  { code: 'fr', label: 'Français', native: 'FR' },
  { code: 'ti', label: 'ትግርኛ', native: 'TI' },
  { code: 'lg', label: 'Luganda', native: 'LG' },
  { code: 'aa', label: 'Qafar af', native: 'AA' },
];

export function LanguageSelector({
  value,
  onChange,
  className,
}: {
  value: Language;
  onChange: (l: Language) => void;
  className?: string;
}) {
  return (
    <Select value={value} onValueChange={(v) => onChange(v as Language)}>
      <SelectTrigger className={cn('h-8 w-36 gap-1.5 text-xs', className)} aria-label="Select language">
        <Languages className="h-3.5 w-3.5 shrink-0 text-muted-foreground" />
        <SelectValue />
      </SelectTrigger>
      <SelectContent>
        {LANGS.map((l) => (
          <SelectItem key={l.code} value={l.code} className="text-xs">
            <span className="mr-1.5 font-mono text-[10px] text-muted-foreground">{l.native}</span>
            {l.label}
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  );
}
