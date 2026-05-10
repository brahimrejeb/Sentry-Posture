import type { Mode } from '../api';
import type { ViewName } from '../hooks/useView';

const ALL_TABS: { id: ViewName; label: string; advanced?: boolean }[] = [
  { id: 'live', label: 'Live' },
  { id: 'today', label: 'Today', advanced: true },
  { id: 'week', label: 'Week', advanced: true },
  { id: 'month', label: 'Month', advanced: true },
  { id: 'year', label: 'Year', advanced: true },
  { id: 'settings', label: 'Settings' },
];

export function Tabs({
  view,
  onChange,
  mode,
}: {
  view: ViewName;
  onChange: (next: ViewName) => void;
  mode: Mode;
}) {
  const tabs = ALL_TABS.filter((t) => mode === 'advanced' || !t.advanced);
  return (
    <nav className="tabs" role="tablist">
      {tabs.map((t) => (
        <button
          key={t.id}
          role="tab"
          aria-selected={view === t.id}
          className={`tab ${view === t.id ? 'tab-active' : ''}`}
          onClick={() => onChange(t.id)}
        >
          {t.label}
        </button>
      ))}
    </nav>
  );
}
