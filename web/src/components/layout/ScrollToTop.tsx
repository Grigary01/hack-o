import { useEffect } from 'react';
import { useLocation } from 'react-router-dom';

/** При переходе между экранами — наверх; фокус переносится на <main>, чтобы скринридер начал с контента. */
export function ScrollToTop() {
  const { pathname } = useLocation();
  useEffect(() => {
    window.scrollTo({ top: 0 });
    const main = document.getElementById('main');
    if (main && document.activeElement && document.activeElement !== document.body) main.focus({ preventScroll: true });
  }, [pathname]);
  return null;
}
