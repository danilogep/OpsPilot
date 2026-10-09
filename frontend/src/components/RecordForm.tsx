import { useForm } from "react-hook-form";
import { z } from "zod";
import { Input, Select, Textarea } from "@/components/ui/Field";
import { Button } from "@/components/ui/Button";
import { ActionError, useAction } from "@/components/Data";

export interface FormField {
  key: string;
  label: string;
  type?: string;
  required?: boolean;
  options?: { value: string; label: string }[];
}
export function RecordForm({
  fields,
  initial = {},
  submit,
  onDone,
  submitLabel = "Salvar",
}: {
  fields: FormField[];
  initial?: Record<string, unknown>;
  submit: (data: Record<string, unknown>) => Promise<unknown>;
  onDone?: () => void;
  submitLabel?: string;
}) {
  const {
    register,
    handleSubmit,
    setError,
    formState: { errors },
  } = useForm<Record<string, string>>({
    defaultValues: Object.fromEntries(
      fields.map((f) => [f.key, String(initial[f.key] ?? "")]),
    ),
  });
  const action = useAction(submit);
  return (
    <form
      className="space-y-4"
      onSubmit={handleSubmit((values) => {
        let valid = true;
        const payload: Record<string, unknown> = {};
        fields.forEach((f) => {
          const value = values[f.key]?.trim() ?? "";
          if (f.required && !value) {
            setError(f.key, { message: "Preencha este campo." });
            valid = false;
          } else if (
            f.type === "email" &&
            value &&
            !z.string().email().safeParse(value).success
          ) {
            setError(f.key, { message: "Informe um e-mail válido." });
            valid = false;
          }
          payload[f.key] =
            f.type === "number" ? Number(value || 0) : value || null;
        });
        if (valid) action.mutate(payload, { onSuccess: onDone });
      })}
    >
      <div className="grid gap-4 sm:grid-cols-2">
        {fields.map((f) => {
          const props = {
            label: f.label,
            required: f.required,
            error: errors[f.key]?.message,
            ...register(f.key),
          };
          return f.options ? (
            <Select
              key={f.key}
              {...props}
              options={f.options}
              placeholder="Selecione"
            />
          ) : f.type === "textarea" ? (
            <Textarea key={f.key} {...props} />
          ) : (
            <Input
              key={f.key}
              {...props}
              type={f.type ?? "text"}
              min={f.type === "number" ? 0 : undefined}
              step={f.type === "number" ? ".01" : undefined}
            />
          );
        })}
      </div>
      <ActionError error={action.error} />
      <Button type="submit" loading={action.isPending}>
        {submitLabel}
      </Button>
    </form>
  );
}
