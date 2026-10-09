import clsx from "clsx";
import type { ReactNode } from "react";

/**
 * Renderiza o texto gerado pela IA.
 *
 * O backend devolve um Markdown mínimo (negrito, itálico, listas com `-` e
 * listas numeradas). Aqui ele vira **elementos React**, nunca HTML injetado:
 * o conteúdo vem de um modelo de linguagem e de documentos enviados pelo
 * usuário, então tratá-lo como marcação executável seria um vetor de XSS.
 * O que não for reconhecido aparece como texto puro.
 */

const BOLD_OR_ITALIC = /(\*\*[^*]+\*\*|_[^_]+_)/g;

/** Converte `**negrito**` e `_itálico_` em elementos, preservando o resto. */
function renderInline(text: string): ReactNode[] {
  return text.split(BOLD_OR_ITALIC).map((part, index) => {
    if (part.startsWith("**") && part.endsWith("**") && part.length > 4) {
      return <strong key={index}>{part.slice(2, -2)}</strong>;
    }
    if (part.startsWith("_") && part.endsWith("_") && part.length > 2) {
      return <em key={index}>{part.slice(1, -1)}</em>;
    }
    return part;
  });
}

type Block =
  | { kind: "paragraph"; lines: string[] }
  | { kind: "bullets"; items: string[] }
  | { kind: "numbers"; items: string[] };

const BULLET = /^[-*]\s+/;
const NUMBERED = /^\d+\.\s+/;

/** Agrupa as linhas em parágrafos e listas. */
export function parseAnswer(text: string): Block[] {
  const blocks: Block[] = [];
  let current: Block | null = null;

  const flush = (): void => {
    if (current) blocks.push(current);
    current = null;
  };

  for (const rawLine of text.replace(/\r\n/g, "\n").split("\n")) {
    const line = rawLine.trim();
    if (!line) {
      flush();
      continue;
    }
    if (BULLET.test(line)) {
      if (current?.kind !== "bullets") {
        flush();
        current = { kind: "bullets", items: [] };
      }
      current.items.push(line.replace(BULLET, ""));
      continue;
    }
    if (NUMBERED.test(line)) {
      if (current?.kind !== "numbers") {
        flush();
        current = { kind: "numbers", items: [] };
      }
      current.items.push(line.replace(NUMBERED, ""));
      continue;
    }
    if (current?.kind !== "paragraph") {
      flush();
      current = { kind: "paragraph", lines: [] };
    }
    current.lines.push(line);
  }
  flush();
  return blocks;
}

export interface AnswerTextProps {
  text: string;
  className?: string;
  /** Identificador para os testes automatizados. */
  "data-testid"?: string;
}

export function AnswerText({
  text,
  className,
  "data-testid": testId,
}: AnswerTextProps): JSX.Element {
  const blocks = parseAnswer(text);
  return (
    <div className={clsx("prose-answer", className)} data-testid={testId}>
      {blocks.map((block, index) => {
        if (block.kind === "bullets") {
          return (
            <ul key={index}>
              {block.items.map((item, itemIndex) => (
                <li key={itemIndex}>{renderInline(item)}</li>
              ))}
            </ul>
          );
        }
        if (block.kind === "numbers") {
          return (
            <ol key={index}>
              {block.items.map((item, itemIndex) => (
                <li key={itemIndex}>{renderInline(item)}</li>
              ))}
            </ol>
          );
        }
        return (
          <p key={index}>
            {block.lines.map((line, lineIndex) => (
              <span key={lineIndex}>
                {lineIndex > 0 ? <br /> : null}
                {renderInline(line)}
              </span>
            ))}
          </p>
        );
      })}
    </div>
  );
}
