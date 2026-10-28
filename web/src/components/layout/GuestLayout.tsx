import type { ReactNode } from 'react';
import { SiteFooter } from './SiteFooter';
import { SiteHeader } from './SiteHeader';
import { SkipLink } from './SkipLink';
import styles from './GuestLayout.module.css';

export function GuestLayout({ context, children }: { context?: string | null; children: ReactNode }) {
  return (
    <div className={styles.page}>
      <SkipLink />
      <SiteHeader context={context} />
      <main id="main" className={styles.main} tabIndex={-1}>
        {children}
      </main>
      <SiteFooter />
    </div>
  );
}
