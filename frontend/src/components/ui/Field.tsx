import clsx from "clsx";
import { forwardRef, useId } from "react";
import type {
  InputHTMLAttributes,
  ReactNode,
  SelectHTMLAttributes,
  TextareaHTMLAttributes,
} from "react";

interface BaseFieldProps {
  label?: string;
  error?: string;
  hint?: ReactNode;
  required?: boolean;
  className?: string;
}

function FieldShell({
  id,
  label,
  error,
  hint,
  required,
  className,
  children,
}: BaseFieldProps & { id: string; children: ReactNode }): JSX.Element {
  return (
    <div className={clsx("w-full", className)}>
      {label ? (
        <label className="label" htmlFor={id}>
          {label}
          {required ? (
            <span aria-hidden="true" className="ml-0.5 text-danger-600">
              *
            </span>
          ) : null}
        </label>
      ) : null}
      {children}
      {error ? (
        <p
          id={`${id}-error`}
          role="alert"
          className="mt-1 text-xs text-danger-700"
        >
          {error}
        </p>
      ) : hint ? (
        <p className="mt-1 text-xs text-ink-500">{hint}</p>
      ) : null}
    </div>
  );
}

export type InputProps = BaseFieldProps & InputHTMLAttributes<HTMLInputElement>;

export const Input = forwardRef<HTMLInputElement, InputProps>(function Input(
  { label, error, hint, className, required, id, ...rest },
  ref,
) {
  const generatedId = useId();
  const fieldId = id ?? generatedId;
  return (
    <FieldShell
      id={fieldId}
      label={label}
      error={error}
      hint={hint}
      required={required}
      className={className}
    >
      <input
        ref={ref}
        required={required}
        id={fieldId}
        aria-invalid={error ? true : undefined}
        aria-describedby={error ? `${fieldId}-error` : undefined}
        className={clsx("field", error && "field-error")}
        {...rest}
      />
    </FieldShell>
  );
});

export interface SelectOption {
  value: string;
  label: string;
}

export type SelectProps = BaseFieldProps &
  SelectHTMLAttributes<HTMLSelectElement> & {
    options: SelectOption[];
    placeholder?: string;
  };

export const Select = forwardRef<HTMLSelectElement, SelectProps>(
  function Select(
    {
      label,
      error,
      hint,
      className,
      required,
      id,
      options,
      placeholder,
      ...rest
    },
    ref,
  ) {
    const generatedId = useId();
    const fieldId = id ?? generatedId;
    return (
      <FieldShell
        id={fieldId}
        label={label}
        error={error}
        hint={hint}
        required={required}
        className={className}
      >
        <select
          ref={ref}
          required={required}
          id={fieldId}
          aria-invalid={error ? true : undefined}
          className={clsx("field", error && "field-error")}
          {...rest}
        >
          {placeholder ? <option value="">{placeholder}</option> : null}
          {options.map((option) => (
            <option key={option.value} value={option.value}>
              {option.label}
            </option>
          ))}
        </select>
      </FieldShell>
    );
  },
);

export type TextareaProps = BaseFieldProps &
  TextareaHTMLAttributes<HTMLTextAreaElement>;

export const Textarea = forwardRef<HTMLTextAreaElement, TextareaProps>(
  function Textarea(
    { label, error, hint, className, required, id, rows = 4, ...rest },
    ref,
  ) {
    const generatedId = useId();
    const fieldId = id ?? generatedId;
    return (
      <FieldShell
        id={fieldId}
        label={label}
        error={error}
        hint={hint}
        required={required}
        className={className}
      >
        <textarea
          ref={ref}
          required={required}
          id={fieldId}
          rows={rows}
          aria-invalid={error ? true : undefined}
          aria-describedby={error ? `${fieldId}-error` : undefined}
          className={clsx("field resize-y", error && "field-error")}
          {...rest}
        />
      </FieldShell>
    );
  },
);

export interface CheckboxProps extends InputHTMLAttributes<HTMLInputElement> {
  label: string;
}

export function Checkbox({
  label,
  className,
  id,
  ...rest
}: CheckboxProps): JSX.Element {
  const generatedId = useId();
  const fieldId = id ?? generatedId;
  return (
    <label
      htmlFor={fieldId}
      className={clsx(
        "inline-flex cursor-pointer items-center gap-2 text-sm text-ink-700",
        className,
      )}
    >
      <input
        id={fieldId}
        type="checkbox"
        className="h-4 w-4 rounded border-ink-300 text-brand-700 focus:ring-brand-200"
        {...rest}
      />
      {label}
    </label>
  );
}
