import { useId } from 'react';
import styles from './HotelIllustration.module.css';

/** Палитры повторяют макет и слегка варьируются, чтобы карточки различались. */
const PALETTES = [
  { bg: '#e1eaf5', wall: '#d6e1ef', curtain: '#92a7c2', window: '#bad4f3', sky: '#d4e6fb', bed: '#ffffff', base: '#a9bbd0', accent: '#1765ee' },
  { bg: '#e4ecf4', wall: '#d9e4ee', curtain: '#8fa3b8', window: '#c4dbef', sky: '#dcebf8', bed: '#ffffff', base: '#a4b6c9', accent: '#07766a' },
  { bg: '#e2e9f6', wall: '#d5dff0', curtain: '#98a6c6', window: '#b8cdf2', sky: '#d1e0fa', bed: '#ffffff', base: '#a7b4d0', accent: '#5b6fd6' },
  { bg: '#e8ebf1', wall: '#dde2ea', curtain: '#a1aabb', window: '#c9d6e8', sky: '#e0e8f3', bed: '#ffffff', base: '#b0b9c8', accent: '#8a5b00' },
  { bg: '#e0ebf3', wall: '#d2e2ee', curtain: '#8aa6bd', window: '#b2d4ee', sky: '#cde5f7', bed: '#ffffff', base: '#a2b9cc', accent: '#0f56d6' },
] as const;

interface Props {
  variant?: number;
  caption?: string;
  /** Широкий кадр для карточки номера. */
  wide?: boolean;
  className?: string;
}

export function HotelIllustration({ variant = 0, caption = 'Иллюстрация · фото не подключены', wide, className }: Props) {
  const p = PALETTES[Math.abs(variant) % PALETTES.length]!;
  const gid = useId();
  return (
    <figure className={[styles.frame, wide ? styles.wide : '', className].filter(Boolean).join(' ')} style={{ background: p.bg }}>
      <svg
        className={styles.svg}
        viewBox={wide ? '0 0 780 250' : '0 0 176 176'}
        preserveAspectRatio={wide ? 'xMidYMid slice' : 'xMidYMid meet'}
        aria-hidden="true"
      >
        <defs>
          <linearGradient id={`${gid}-sky`} x1="0" y1="0" x2="0" y2="1">
            <stop offset="0" stopColor={p.sky} />
            <stop offset="1" stopColor={p.window} />
          </linearGradient>
        </defs>
        {wide ? (
          <g>
            <rect x="0" y="0" width="780" height="250" fill={p.wall} opacity="0.55" />
            <rect x="34" y="20" width="250" height="116" rx="6" fill={`url(#${gid}-sky)`} />
            <path d="M34 112 Q110 94 180 106 T284 100 V136 H34Z" fill={p.window} opacity="0.9" />
            <rect x="157" y="20" width="4" height="116" fill={p.bg} />
            <rect x="18" y="14" width="20" height="150" rx="4" fill={p.curtain} />
            <rect x="282" y="14" width="10" height="150" rx="4" fill={p.curtain} opacity="0.65" />
            <rect x="14" y="10" width="290" height="6" rx="3" fill={p.base} />
            <rect x="560" y="96" width="44" height="64" rx="4" fill={p.base} opacity="0.6" />
            <circle cx="582" cy="86" r="14" fill={p.bed} />
            <rect x="579" y="96" width="6" height="18" fill={p.base} />
            <rect x="356" y="98" width="200" height="20" rx="6" fill={p.base} opacity="0.75" />
            <rect x="312" y="120" width="430" height="60" rx="8" fill={p.bed} />
            <rect x="330" y="104" width="86" height="30" rx="10" fill={p.bed} stroke={p.base} strokeWidth="2" />
            <rect x="428" y="104" width="86" height="30" rx="10" fill={p.bed} stroke={p.base} strokeWidth="2" />
            <rect x="520" y="134" width="222" height="46" rx="6" fill={p.accent} opacity="0.12" />
            <rect x="296" y="180" width="462" height="12" rx="4" fill={p.base} />
          </g>
        ) : (
          <g>
            <rect x="34" y="20" width="44" height="78" rx="3" fill={`url(#${gid}-sky)`} />
            <path d="M34 82 Q50 76 62 80 T78 78 V98 H34Z" fill={p.window} />
            <rect x="16" y="14" width="20" height="106" rx="3" fill={p.curtain} />
            <rect x="12" y="10" width="72" height="4" rx="2" fill={p.base} />
            <rect x="80" y="74" width="42" height="12" rx="4" fill={p.base} opacity="0.7" />
            <rect x="70" y="86" width="92" height="40" rx="5" fill={p.bed} />
            <rect x="78" y="76" width="34" height="18" rx="6" fill={p.bed} stroke={p.base} strokeWidth="1.5" />
            <rect x="116" y="100" width="46" height="26" rx="4" fill={p.accent} opacity="0.12" />
            <rect x="66" y="126" width="100" height="8" rx="3" fill={p.base} />
          </g>
        )}
      </svg>
      {caption && <figcaption className={styles.caption}>{caption}</figcaption>}
    </figure>
  );
}
