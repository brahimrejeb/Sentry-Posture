import { useEffect, useState } from 'react';

const KEY = 'view';
export type ViewName = 'live' | 'today' | 'week' | 'month' | 'year' | 'settings';

export const VIEWS: ViewName[] = ['live', 'today', 'week', 'month', 'year', 'settings'];

function readView(): ViewName {
  const search = new URLSearchParams(window.location.search);
  const value = search.get(KEY) as ViewName | null;
  return value && VIEWS.includes(value) ? value : 'live';
}

export function useView(): [ViewName, (next: ViewName) => void] {
  const [view, setView] = useState<ViewName>(readView);

  useEffect(() => {
    const onPop = () => setView(readView());
    window.addEventListener('popstate', onPop);
    return () => window.removeEventListener('popstate', onPop);
  }, []);

  const navigate = (next: ViewName) => {
    const url = new URL(window.location.href);
    if (next === 'live') {
      url.searchParams.delete(KEY);
    } else {
      url.searchParams.set(KEY, next);
    }
    window.history.pushState({}, '', url);
    setView(next);
  };

  return [view, navigate];
}
