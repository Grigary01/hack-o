import { useMemo } from 'react';
import styles from './SchematicMap.module.css';

export interface MapPin {
  id: string;
  name: string;
  label: string;
  coords: { lat: number; lon: number };
  tone: 'confirmed' | 'partial' | 'excluded';
}

interface Props {
  pins: MapPin[];
  /** Где море на схеме: в демо — справа, как в макете; в Адлере — на юго-западе. */
  seaSide: 'east' | 'southwest' | null;
  activeId: string | null;
  onSelect: (id: string) => void;
  onHover?: (id: string | null) => void;
  caption: string;
}

/** Области суши, куда проецируются отели, чтобы метки не попадали в море. */
const LAND = {
  east: { x0: 0.08, x1: 0.56, y0: 0.08, y1: 0.86 },
  southwest: { x0: 0.2, x1: 0.9, y0: 0.08, y1: 0.74 },
  none: { x0: 0.1, x1: 0.9, y0: 0.08, y1: 0.88 },
} as const;

function project(pins: MapPin[], seaSide: Props['seaSide']) {
  const area = LAND[seaSide ?? 'none'];
  const lats = pins.map((p) => p.coords.lat);
  const lons = pins.map((p) => p.coords.lon);
  const [minLat, maxLat] = [Math.min(...lats), Math.max(...lats)];
  const [minLon, maxLon] = [Math.min(...lons), Math.max(...lons)];
  const spanLat = maxLat - minLat || 1;
  const spanLon = maxLon - minLon || 1;
  return pins.map((p) => {
    const nx = pins.length === 1 ? 0.5 : (p.coords.lon - minLon) / spanLon;
    const ny = pins.length === 1 ? 0.5 : 1 - (p.coords.lat - minLat) / spanLat;
    return { ...p, x: area.x0 + nx * (area.x1 - area.x0), y: area.y0 + ny * (area.y1 - area.y0) };
  });
}

export function SchematicMap({ pins, seaSide, activeId, onSelect, onHover, caption }: Props) {
  const placed = useMemo(() => project(pins, seaSide), [pins, seaSide]);
  // Активная метка рисуется последней, чтобы не пряталась под соседями.
  const ordered = [...placed].sort((a, b) => Number(a.id === activeId) - Number(b.id === activeId));

  return (
    <div className={styles.map} role="group" aria-label="Схематическая карта отелей">
      <svg className={styles.base} viewBox="0 0 360 680" preserveAspectRatio="none" aria-hidden="true">
        <rect width="360" height="680" fill="var(--c-map-land)" />
        {seaSide === 'east' && (
          <g>
            {[40, 150].map((x) => (
              <rect key={x} x={x} y="0" width="12" height="680" fill="var(--c-map-road)" />
            ))}
            {[90, 225, 350, 480].map((y) => (
              <rect key={y} x="0" y={y} width="210" height="12" fill="var(--c-map-road)" />
            ))}
            <rect x="198" y="0" width="12" height="680" fill="var(--c-map-road)" />
            <rect x="210" y="0" width="150" height="680" fill="var(--c-map-sea)" />
          </g>
        )}
        {seaSide === 'southwest' && (
          <g>
            {[70, 170, 270].map((x) => (
              <rect key={x} x={x} y="0" width="10" height="680" fill="var(--c-map-road)" transform={`skewX(-8)`} />
            ))}
            {[110, 260, 400].map((y) => (
              <rect key={y} x="0" y={y} width="360" height="10" fill="var(--c-map-road)" />
            ))}
            <path d="M0 520 Q60 560 120 620 T190 680 H0Z" fill="var(--c-map-sea)" />
            <path d="M0 520 Q60 560 120 620 T190 680" fill="none" stroke="var(--c-map-road)" strokeWidth="8" />
          </g>
        )}
        {seaSide === null && (
          <g>
            {[60, 180, 300].map((x) => (
              <rect key={x} x={x} y="0" width="10" height="680" fill="var(--c-map-road)" />
            ))}
            {[120, 300, 480].map((y) => (
              <rect key={y} x="0" y={y} width="360" height="10" fill="var(--c-map-road)" />
            ))}
          </g>
        )}
      </svg>

      {seaSide && (
        <span className={`${styles.seaLabel} ${seaSide === 'east' ? styles.seaEast : styles.seaSouthwest}`} aria-hidden="true">
          Море
        </span>
      )}

      {ordered.map((pin) => {
        const active = pin.id === activeId;
        return (
          <button
            key={pin.id}
            type="button"
            className={[styles.pin, styles[pin.tone], active ? styles.active : ''].filter(Boolean).join(' ')}
            style={{ left: `${pin.x * 100}%`, top: `${pin.y * 100}%` }}
            aria-label={`${pin.name}: ${pin.label}. Показать в списке`}
            aria-pressed={active}
            onClick={() => onSelect(pin.id)}
            onMouseEnter={() => onHover?.(pin.id)}
            onMouseLeave={() => onHover?.(null)}
            onFocus={() => onHover?.(pin.id)}
            onBlur={() => onHover?.(null)}
          >
            <span className={styles.pinLabel}>{pin.label}</span>
            {active && <span className={styles.pinName}>{pin.name}</span>}
          </button>
        );
      })}

      <p className={styles.caption}>{caption}</p>
    </div>
  );
}
