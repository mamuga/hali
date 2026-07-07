import { NavLink } from 'react-router-dom';
import { Bell, BookOpen, Map, Radio } from 'lucide-react';
import { cn } from '@/lib/utils';

const LINKS = [
  { to: '/', label: 'Alerts', Icon: Bell },
  { to: '/map', label: 'Map', Icon: Map },
  { to: '/actions', label: 'Actions', Icon: BookOpen },
  { to: '/report', label: 'Report', Icon: Radio },
];

export function BottomNav() {
  return (
    <nav
      aria-label="Main navigation"
      className="fixed inset-x-0 bottom-0 z-50 flex h-16 items-stretch border-t border-border bg-card/95 pb-[env(safe-area-inset-bottom)] backdrop-blur-sm"
    >
      {LINKS.map(({ to, label, Icon }) => (
        <NavLink
          key={to}
          to={to}
          end={to === '/'}
          aria-label={label}
          className={({ isActive }) =>
            cn(
              'flex flex-1 flex-col items-center justify-center gap-1 text-[10px] font-medium tracking-wide no-underline transition-colors duration-150',
              isActive ? 'text-primary' : 'text-muted-foreground hover:text-foreground',
            )
          }
        >
          {({ isActive }) => (
            <>
              <Icon className={cn('h-5 w-5 transition-all duration-150', isActive && 'scale-110')} strokeWidth={isActive ? 2 : 1.5} />
              <span>{label}</span>
            </>
          )}
        </NavLink>
      ))}
    </nav>
  );
}
