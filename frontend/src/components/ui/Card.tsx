import clsx from "clsx";
import type { ReactNode } from "react";

export interface CardProps {
  children: ReactNode;
  className?: string;
}

export function Card({ children, className }: CardProps): JSX.Element {
  return <section className={clsx("card", className)}>{children}</section>;
}

export interface CardHeaderProps {
  title: ReactNode;
  subtitle?: ReactNode;
  actions?: ReactNode;
  className?: string;
}

export function CardHeader({
  title,
  subtitle,
  actions,
  className,
}: CardHeaderProps): JSX.Element {
  return (
    <header className={clsx("card-header", className)}>
      <div className="min-w-0">
        <h2 className="card-title">{title}</h2>
        {subtitle ? <p className="card-subtitle mt-0.5">{subtitle}</p> : null}
      </div>
      {actions ? (
        <div className="flex flex-wrap items-center gap-2">{actions}</div>
      ) : null}
    </header>
  );
}

export function CardBody({ children, className }: CardProps): JSX.Element {
  return <div className={clsx("px-5 py-4", className)}>{children}</div>;
}

export function CardFooter({ children, className }: CardProps): JSX.Element {
  return (
    <footer
      className={clsx(
        "border-t border-ink-100 px-5 py-3 text-sm text-ink-500",
        className,
      )}
    >
      {children}
    </footer>
  );
}

export interface PageHeaderProps {
  title: string;
  description?: string;
  actions?: ReactNode;
}

export function PageHeader({
  title,
  description,
  actions,
}: PageHeaderProps): JSX.Element {
  return (
    <div className="mb-6 flex flex-wrap items-end justify-between gap-3">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight text-ink-900">
          {title}
        </h1>
        {description ? (
          <p className="mt-1 max-w-3xl text-sm text-ink-500">{description}</p>
        ) : null}
      </div>
      {actions ? (
        <div className="flex flex-wrap items-center gap-2">{actions}</div>
      ) : null}
    </div>
  );
}
