import { useState } from 'react';
import { HaliMap } from '@/components/HaliMap';
import { LanguageSelector } from '@/components/LanguageSelector';
import type { Language } from '@hali/types';

export function MapView() {
  const [lang, setLang] = useState<Language>('sw');
  return (
    <div className="relative h-full">
      <div className="absolute left-3 top-3 z-[1000]">
        <LanguageSelector value={lang} onChange={setLang} />
      </div>
      <HaliMap lang={lang} />
    </div>
  );
}
