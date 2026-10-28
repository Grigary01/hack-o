import { useId, type InputHTMLAttributes, type ReactNode, type SelectHTMLAttributes, type TextareaHTMLAttributes } from 'react';
import styles from './Field.module.css';

interface BoxProps {
  label: string;
  hint?: ReactNode;
  className?: string;
}

/** Поле в стиле макета: подпись мелким шрифтом внутри рамки, значение крупнее. */
export function TextField({ label, hint, className, suffix, ...input }: BoxProps & InputHTMLAttributes<HTMLInputElement> & { suffix?: string }) {
  const generated = useId();
  const id = input.id ?? generated;
  const hintId = hint ? `${id}-hint` : undefined;
  return (
    <div className={[styles.wrap, className].filter(Boolean).join(' ')}>
      <label className={`${styles.box} ${input.disabled ? styles.disabled : ''}`} htmlFor={id}>
        <span className={styles.label}>{label}</span>
        <span className={styles.control}>
          <input {...input} id={id} className={styles.input} aria-describedby={[hintId, input['aria-describedby']].filter(Boolean).join(' ') || undefined} />
          {suffix && (
            <span className={styles.suffix} aria-hidden="true">
              {suffix}
            </span>
          )}
        </span>
      </label>
      {hint && (
        <p id={hintId} className={styles.hint}>
          {hint}
        </p>
      )}
    </div>
  );
}

export function SelectField({ label, hint, className, children, ...select }: BoxProps & SelectHTMLAttributes<HTMLSelectElement>) {
  const generated = useId();
  const id = select.id ?? generated;
  const hintId = hint ? `${id}-hint` : undefined;
  return (
    <div className={[styles.wrap, className].filter(Boolean).join(' ')}>
      <label className={`${styles.box} ${styles.selectBox}`} htmlFor={id}>
        <span className={styles.label}>{label}</span>
        <select {...select} id={id} className={`${styles.input} ${styles.select}`} aria-describedby={hintId}>
          {children}
        </select>
        <svg className={styles.chevron} width="12" height="12" viewBox="0 0 12 12" aria-hidden="true">
          <path d="M2.5 4.5 6 8l3.5-3.5" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" />
        </svg>
      </label>
      {hint && (
        <p id={hintId} className={styles.hint}>
          {hint}
        </p>
      )}
    </div>
  );
}

export function TextArea({ label, hint, className, labelVisible = true, ...area }: BoxProps & TextareaHTMLAttributes<HTMLTextAreaElement> & { labelVisible?: boolean }) {
  const generated = useId();
  const id = area.id ?? generated;
  const hintId = hint ? `${id}-hint` : undefined;
  return (
    <div className={[styles.wrap, className].filter(Boolean).join(' ')}>
      <label className={labelVisible ? styles.areaLabel : 'visually-hidden'} htmlFor={id}>
        {label}
      </label>
      <textarea {...area} id={id} className={styles.area} aria-describedby={[hintId, area['aria-describedby']].filter(Boolean).join(' ') || undefined} />
      {hint && (
        <p id={hintId} className={styles.hint}>
          {hint}
        </p>
      )}
    </div>
  );
}

export function Checkbox({ label, className, ...input }: { label: ReactNode; className?: string } & Omit<InputHTMLAttributes<HTMLInputElement>, 'type'>) {
  return (
    <label className={[styles.check, className].filter(Boolean).join(' ')}>
      <input type="checkbox" className={styles.checkInput} {...input} />
      <span className={styles.checkMark} aria-hidden="true">
        <svg width="12" height="12" viewBox="0 0 12 12">
          <path d="m2.5 6.2 2.3 2.3 4.7-5" fill="none" stroke="#fff" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" />
        </svg>
      </span>
      <span>{label}</span>
    </label>
  );
}

export function RadioGroup<T extends string>({
  legend,
  name,
  value,
  options,
  onChange,
  disabled,
}: {
  legend: string;
  name: string;
  value: T;
  options: { value: T; label: string }[];
  onChange: (value: T) => void;
  disabled?: boolean;
}) {
  return (
    <fieldset className={styles.fieldset} disabled={disabled}>
      <legend className={styles.legend}>{legend}</legend>
      {options.map((option) => (
        <label key={option.value} className={styles.check}>
          <input
            type="radio"
            name={name}
            className={styles.radioInput}
            value={option.value}
            checked={value === option.value}
            onChange={() => onChange(option.value)}
          />
          <span className={styles.radioMark} aria-hidden="true" />
          <span>{option.label}</span>
        </label>
      ))}
    </fieldset>
  );
}
