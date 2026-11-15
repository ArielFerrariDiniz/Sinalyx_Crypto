import type { ReactNode } from 'react';

export function Notice({ children, kind = 'info' }: { children: ReactNode; kind?: 'info' | 'error' | 'warning' | 'success' }) {
  return <div className={`notice notice-${kind}`} role={kind === 'error' ? 'alert' : 'status'}>{children}</div>;
}
