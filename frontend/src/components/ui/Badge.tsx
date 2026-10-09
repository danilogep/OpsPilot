import clsx from "clsx";
import type { ReactNode } from "react";

import type { Tone } from "@/lib/labels";

const TONES: Record<Tone, string> = {
  neutral: "bg-ink-100 text-ink-700 ring-ink-200",
  brand: "bg-brand-50 text-brand-800 ring-brand-200",
  success: "bg-success-50 text-success-700 ring-success-100",
  warning: "bg-warning-50 text-warning-700 ring-warning-100",
  danger: "bg-danger-50 text-danger-700 ring-danger-100",
};

export interface BadgeProps {
  children: ReactNode;
  tone?: Tone;
  className?: string;
  title?: string;
}

/** Etiqueta de estado com contraste adequado para texto pequeno. */
export function Badge({
  children,
  tone = "neutral",
  className,
  title,
}: BadgeProps): JSX.Element {
  return (
    <span
      title={title}
      className={clsx(
        "inline-flex items-center gap-1 whitespace-nowrap rounded-full px-2.5 py-0.5",
        "text-xs font-medium ring-1 ring-inset",
        TONES[tone],
        className,
      )}
    >
      {children}
    </span>
  );
}

export interface ScoreBadgeProps {
  score: number;
  className?: string;
}

/** Score 0–100 com cor derivada das faixas usadas no backend. */
export function ScoreBadge({ score, className }: ScoreBadgeProps): JSX.Element {
  const tone: Tone =
    score >= 70 ? "danger" : score >= 45 ? "warning" : "neutral";
  return (
    <Badge
      tone={tone}
      className={clsx("font-mono", className)}
      title={`Score ${score} de 100`}
    >
      {score}
    </Badge>
  );
}
