import { Link, Outlet, useLocation, useNavigate, useParams } from 'react-router-dom';
import { SiteFooter } from '../../components/layout/SiteFooter';
import { SiteHeader } from '../../components/layout/SiteHeader';
import { SkipLink } from '../../components/layout/SkipLink';
import { SelectField } from '../../components/ui/Field';
import { useHotelierHotels } from '../../data';
import type { CabinetContext } from './cabinetContext';
import styles from './CabinetLayout.module.css';


type Section = 'overview' | 'questions' | 'facts' | 'rooms';

const NAV: { key: Section; label: string }[] = [
  { key: 'overview', label: 'Обзор' },
  { key: 'questions', label: 'Вопросы' },
  { key: 'facts', label: 'Характеристики' },
  { key: 'rooms', label: 'Номера' },
];

function sectionOf(pathname: string): Section {
  if (pathname.endsWith('/published')) return 'facts';
  if (/\/(questions|answers)(\/|$)/.test(pathname)) return 'questions';
  if (pathname.endsWith('/facts')) return 'facts';
  if (pathname.endsWith('/rooms')) return 'rooms';
  return 'overview';
}

export function CabinetLayout() {
  const { hotelId = '' } = useParams();
  const { pathname } = useLocation();
  const navigate = useNavigate();
  const hotels = useHotelierHotels();
  const current = hotels.data?.find((h) => h.id === hotelId);
  const hotelName = current?.name ?? '';
  const base = `/hotelier/${encodeURIComponent(hotelId)}`;
  const active = sectionOf(pathname);
  const open = current?.openQuestions ?? 0;

  return (
    <div className={styles.page}>
      <SkipLink />
      <SiteHeader cabinet context={hotelName ? `${hotelName} · Представитель отеля` : null} />
      <div className={styles.body}>
        <aside className={styles.sidebar}>
          <nav aria-label="Кабинет отельера">
            <ul className={styles.nav}>
              {NAV.map((item) => (
                <li key={item.key}>
                  <Link
                    to={`${base}/${item.key}`}
                    className={`${styles.navLink} ${active === item.key ? styles.navActive : ''}`}
                    aria-current={active === item.key ? 'page' : undefined}
                  >
                    {item.label}
                    {item.key === 'questions' && open > 0 && (
                      <span className={styles.count}>
                        {open}
                        <span className="visually-hidden"> открытых</span>
                      </span>
                    )}
                  </Link>
                </li>
              ))}
            </ul>
          </nav>

          {hotels.data && hotels.data.length > 1 && (
            <SelectField
              className={styles.switcher}
              label="Отель · демо без входа"
              value={hotelId}
              onChange={(e) => navigate(`/hotelier/${encodeURIComponent(e.target.value)}/questions`)}
            >
              {hotels.data.map((h) => (
                <option key={h.id} value={h.id}>
                  {h.name}
                  {h.openQuestions ? ` (${h.openQuestions})` : ''}
                </option>
              ))}
            </SelectField>
          )}

          <p className={styles.sideNote}>Ответьте один раз — используем в будущих подборах.</p>
        </aside>

        <div className={styles.content}>
          <main id="main" tabIndex={-1} className={styles.main}>
            <Outlet context={{ hotelId, hotelName, base } satisfies CabinetContext} />
          </main>
          <SiteFooter inset />
        </div>
      </div>
    </div>
  );
}
