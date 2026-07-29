import { useEffect, useState } from 'react';
import { Moon, Sun } from 'lucide-react';

/**
 * The only interactive island on the page. The initial class is set by the
 * inline script in Base.astro, so this component only mirrors and flips it.
 */
export default function ThemeToggle() {
  const [dark, setDark] = useState(true);

  useEffect(() => {
    setDark(document.documentElement.classList.contains('dark'));
  }, []);

  function toggle() {
    const next = !dark;
    document.documentElement.classList.toggle('dark', next);
    try {
      localStorage.setItem('hali-theme', next ? 'dark' : 'light');
    } catch {
      /* private browsing — the toggle still works for this page view */
    }
    setDark(next);
  }

  return (
    <button
      type="button"
      onClick={toggle}
      aria-label={dark ? 'Switch to light mode' : 'Switch to dark mode'}
      className="inline-flex h-9 w-9 items-center justify-center rounded-sm border border-border text-muted-foreground transition-colors hover:text-foreground"
    >
      {dark ? <Sun size={18} strokeWidth={1.75} /> : <Moon size={18} strokeWidth={1.75} />}
    </button>
  );
}
