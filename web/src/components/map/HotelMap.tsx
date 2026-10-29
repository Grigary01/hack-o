import { useEffect, useLayoutEffect, useRef, useState } from 'react';
import { LngLatBounds, Map as MapLibreMap, Marker, NavigationControl, setWorkerUrl } from 'maplibre-gl';
import 'maplibre-gl/dist/maplibre-gl.css';
// Воркер MapLibre — ES-модуль со своими импортами: пусть Vite соберёт его целиком,
// иначе в dev предсборка ломает относительный путь («Worker failed to load»).
import workerUrl from 'maplibre-gl/dist/maplibre-gl-worker.mjs?worker&url';
import { SchematicMap, type MapPin } from '../SchematicMap';
import styles from './HotelMap.module.css';

/**
 * Векторная карта OpenFreeMap (данные © OpenStreetMap) без ключей.
 * Нужна сеть и WebGL; если что-то из этого недоступно, показываем SVG-схему —
 * поиск от карты не зависит.
 */
const STYLE_URL = 'https://tiles.openfreemap.org/styles/liberty';
setWorkerUrl(workerUrl);
const LOAD_TIMEOUT_MS = 12_000;
/** Запас по краям: метка — «таблетка» над точкой, ей нужно место сверху и по бокам. */
const FIT_PADDING = { top: 72, bottom: 40, left: 72, right: 72 };

/** Подписи на карте по-русски, где есть name:ru; иначе — как в OSM. */
const ruLabel = (): ['coalesce', ['get', string], ['get', string]] => ['coalesce', ['get', 'name:ru'], ['get', 'name']];

function webglSupported(): boolean {
  try {
    const canvas = document.createElement('canvas');
    return Boolean(canvas.getContext('webgl2') ?? canvas.getContext('webgl'));
  } catch {
    return false;
  }
}

interface Props {
  pins: MapPin[];
  activeId: string | null;
  onSelect: (id: string) => void;
  onHover?: (id: string | null) => void;
  seaSide: 'east' | 'southwest' | null;
  fallbackCaption: string;
}

/**
 * Подписи не должны налезать: идём по меткам в порядке выдачи и оставляем «таблетку»,
 * если она не пересекается с уже показанными; остальные сворачиваем в точку.
 * Выбранная метка показывается всегда.
 */
function declutter(instance: MapLibreMap, order: string[], registry: Map<string, { marker: Marker; el: HTMLButtonElement }>, activeId: string | null) {
  const placed: { x: number; y: number; w: number; h: number }[] = [];
  const ids = activeId && registry.has(activeId) ? [activeId, ...order.filter((id) => id !== activeId)] : order;
  for (const id of ids) {
    const item = registry.get(id);
    if (!item) continue;
    const point = instance.project(item.marker.getLngLat());
    // Ширину меряем, пока метка развёрнута (у точки ширина другая); 0 — ещё не в раскладке.
    if (!item.el.classList.contains(styles.dot!) && item.el.offsetWidth > 0) {
      item.el.dataset.width = String(item.el.offsetWidth);
    }
    const w = Number(item.el.dataset.width || 90) + 8;
    const box = { x: point.x - w / 2, y: point.y - 44, w, h: 40 };
    const collides = placed.some((p) => box.x < p.x + p.w && box.x + box.w > p.x && box.y < p.y + p.h && box.y + box.h > p.y);
    const compact = collides && id !== activeId;
    item.el.classList.toggle(styles.dot!, compact);
    // Слои: точки ниже подписей, выбранная — выше всех.
    item.el.style.setProperty('z-index', id === activeId ? '3' : compact ? '1' : '2');
    if (!compact) placed.push(box);
  }
}

function boundsOf(pins: MapPin[]) {
  const bounds = new LngLatBounds();
  for (const p of pins) bounds.extend([p.coords.lon, p.coords.lat]);
  return bounds;
}

export default function HotelMap({ pins, activeId, onSelect, onHover, seaSide, fallbackCaption }: Props) {
  const container = useRef<HTMLDivElement>(null);
  const map = useRef<MapLibreMap | null>(null);
  const markers = useRef(new Map<string, { marker: Marker; el: HTMLButtonElement }>());
  const handlers = useRef({ onSelect, onHover });
  const boundsRef = useRef<LngLatBounds | null>(null);
  const orderRef = useRef<string[]>([]);
  const activeRef = useRef<string | null>(activeId);
  const [status, setStatus] = useState<'loading' | 'ready' | 'failed'>(() => (webglSupported() ? 'loading' : 'failed'));
  useLayoutEffect(() => {
    handlers.current = { onSelect, onHover };
  });

  // Карта создаётся один раз; метки и границы обновляются отдельными эффектами.
  useEffect(() => {
    if (!container.current || status === 'failed') return;
    let instance: MapLibreMap;
    try {
      instance = new MapLibreMap({
        container: container.current,
        style: STYLE_URL,
        bounds: pins.length ? boundsOf(pins) : undefined,
        fitBoundsOptions: { padding: FIT_PADDING, maxZoom: 15 },
        attributionControl: { compact: true },
        dragRotate: false,
        pitchWithRotate: false,
        cooperativeGestures: false,
      });
    } catch {
      // WebGL есть, но контекст не создался (драйвер, лимит контекстов).
      queueMicrotask(() => setStatus('failed'));
      return;
    }
    map.current = instance;
    instance.addControl(new NavigationControl({ showCompass: false }), 'top-right');
    instance.touchZoomRotate.disableRotation();

    const timer = window.setTimeout(() => {
      if (!instance.loaded()) setStatus('failed');
    }, LOAD_TIMEOUT_MS);
    instance.on('load', () => {
      window.clearTimeout(timer);
      // Контейнер мог поменять размер, пока грузился стиль (sticky-колонка, Suspense).
      instance.resize();
      const current = boundsRef.current;
      if (current) instance.fitBounds(current, { padding: FIT_PADDING, maxZoom: 15, duration: 0 });
      for (const layer of instance.getStyle().layers ?? []) {
        const field = layer.type === 'symbol' ? instance.getLayoutProperty(layer.id, 'text-field') : undefined;
        // Только подписи с названиями; щиты трасс показывают номер дороги (ref) — их не трогаем.
        if (field && /name/.test(JSON.stringify(field))) {
          instance.setLayoutProperty(layer.id, 'text-field', ruLabel());
        }
      }
      setStatus('ready');
    });
    instance.on('error', (event) => {
      // Ошибка одного тайла — не повод прятать карту; не загрузился стиль — показываем схему.
      if (!instance.isStyleLoaded() && !instance.loaded()) {
        const message = String((event as unknown as { error?: { message?: string } }).error?.message ?? '');
        if (/style|Failed to fetch|NetworkError|load/i.test(message)) setStatus('failed');
      }
    });

    // Колонка карты меняет размер после монтирования (sticky, Suspense, кнопка «Карта» на телефоне):
    // пересчитываем холст и снова вписываем все метки.
    const observer = new ResizeObserver(() => {
      instance.resize();
      if (boundsRef.current) instance.fitBounds(boundsRef.current, { padding: FIT_PADDING, maxZoom: 15, duration: 0 });
    });
    observer.observe(container.current);
    const relayout = () => declutter(instance, orderRef.current, markers.current, activeRef.current);
    instance.on('moveend', relayout);
    instance.on('zoomend', relayout);

    const registry = markers.current;
    return () => {
      observer.disconnect();
      window.clearTimeout(timer);
      registry.forEach(({ marker }) => marker.remove());
      registry.clear();
      instance.remove();
      map.current = null;
    };
    // pins для начальных границ; дальше их ведёт эффект ниже.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Метки-«таблетки» с ценой или названием, как на выдаче Островка.
  useEffect(() => {
    const instance = map.current;
    if (!instance) return;
    const registry = markers.current;
    const ids = new Set(pins.map((p) => p.id));
    for (const [id, { marker }] of registry) {
      if (!ids.has(id)) {
        marker.remove();
        registry.delete(id);
      }
    }
    for (const pin of pins) {
      const existing = registry.get(pin.id);
      if (existing) {
        existing.el.querySelector('span')!.textContent = pin.label;
        existing.marker.setLngLat([pin.coords.lon, pin.coords.lat]);
        continue;
      }
      const el = document.createElement('button');
      el.type = 'button';
      el.className = [styles.pin, pin.tone === 'confirmed' ? styles.confirmed : styles.partial].join(' ');
      el.setAttribute('aria-label', `${pin.name}: ${pin.label}. Показать в списке`);
      const label = document.createElement('span');
      label.textContent = pin.label;
      el.append(label);
      el.title = pin.name;
      el.addEventListener('click', (e) => {
        e.stopPropagation();
        handlers.current.onSelect(pin.id);
      });
      el.addEventListener('mouseenter', () => handlers.current.onHover?.(pin.id));
      el.addEventListener('mouseleave', () => handlers.current.onHover?.(null));
      el.addEventListener('focus', () => handlers.current.onHover?.(pin.id));
      el.addEventListener('blur', () => handlers.current.onHover?.(null));
      const marker = new Marker({ element: el, anchor: 'bottom' }).setLngLat([pin.coords.lon, pin.coords.lat]).addTo(instance);
      // Ширина «таблетки» для раскладки; уточняется в declutter, когда метка уже в DOM.
      el.dataset.width = String(Math.max(48, pin.label.length * 9 + 24));
      registry.set(pin.id, { marker, el });
    }
    orderRef.current = pins.map((p) => p.id);
    if (pins.length) {
      boundsRef.current = boundsOf(pins);
      instance.fitBounds(boundsRef.current, { padding: FIT_PADDING, maxZoom: 15, duration: 0 });
    }
    declutter(instance, orderRef.current, registry, activeRef.current);
  }, [pins]);

  // Подсветка выбранного отеля: карточка ↔ метка.
  useEffect(() => {
    for (const [id, { el }] of markers.current) {
      const active = id === activeId;
      el.classList.toggle(styles.active!, active);
      el.setAttribute('aria-pressed', String(active));
    }
    activeRef.current = activeId;
    if (map.current) declutter(map.current, orderRef.current, markers.current, activeId);
  }, [activeId]);

  if (status === 'failed') {
    return (
      <SchematicMap
        pins={pins}
        seaSide={seaSide}
        activeId={activeId}
        onSelect={onSelect}
        onHover={onHover}
        caption={`${fallbackCaption} · подложка карты недоступна`}
      />
    );
  }

  return (
    <div className={styles.wrap} role="group" aria-label="Карта отелей">
      <div ref={container} className={styles.map} />
      {status === 'loading' && <div className={styles.loading} aria-hidden="true" />}
    </div>
  );
}
