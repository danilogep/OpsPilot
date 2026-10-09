import { useForm } from "react-hook-form";
import { z } from "zod";
import { Navigate, useLocation, useNavigate } from "react-router-dom";
import { useAuth } from "@/lib/auth";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Field";
import { errorMessage } from "@/components/ui/States";

const schema = z.object({
  email: z.string().email("Informe um e-mail válido."),
  password: z.string().min(1, "Informe sua senha."),
});
type Credentials = z.infer<typeof schema>;
export function Login() {
  const auth = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const {
    register,
    handleSubmit,
    setError,
    formState: { errors, isSubmitting },
  } = useForm<Credentials>({ defaultValues: { email: "", password: "" } });
  if (auth.isAuthenticated && !auth.isLoading)
    return <Navigate to="/" replace />;
  return (
    <main className="grid min-h-screen lg:grid-cols-2">
      <section className="flex flex-col justify-between bg-ink-900 p-8 text-white lg:p-16">
        <p className="text-2xl font-semibold">
          OpsPilot<span className="text-brand-300">.</span>
        </p>
        <div className="my-12 max-w-lg">
          <span className="text-xs uppercase tracking-[.25em] text-brand-300">
            Dados que viram decisões
          </span>
          <h1 className="mt-5 text-4xl font-semibold leading-tight lg:text-5xl">
            Uma visão clara.
            <br />
            Uma operação conectada.
          </h1>
          <p className="mt-6 text-lg text-ink-300">
            Organize planilhas, acompanhe oportunidades e encontre respostas nos
            dados da sua empresa.
          </p>
          <div className="mt-10 flex flex-wrap gap-3 text-xs text-brand-100">
            <span className="rounded-full border border-ink-600 px-4 py-2">
              Importação inteligente
            </span>
            <span className="rounded-full border border-ink-600 px-4 py-2">
              IA com fontes
            </span>
            <span className="rounded-full border border-ink-600 px-4 py-2">
              Automações
            </span>
          </div>
        </div>
        <p className="text-xs text-ink-400">
          Projeto de portfólio • Dados exclusivamente sintéticos
        </p>
      </section>
      <section className="flex items-center justify-center p-8">
        <div className="w-full max-w-sm">
          <h2 className="text-2xl font-semibold">Bem-vindo ao OpsPilot</h2>
          <p className="mb-8 mt-2 text-sm text-ink-500">
            Entre para acompanhar sua operação.
          </p>
          <form
            className="space-y-5"
            onSubmit={handleSubmit(async (values) => {
              const parsed = schema.safeParse(values);
              if (!parsed.success) {
                parsed.error.issues.forEach((e) =>
                  setError(e.path[0] as keyof Credentials, {
                    message: e.message,
                  }),
                );
                return;
              }
              try {
                await auth.login(values.email, values.password);
                const from = (location.state as { from?: string } | null)?.from;
                navigate(
                  from?.startsWith("/") && !from.startsWith("//") ? from : "/",
                  { replace: true },
                );
              } catch (e) {
                setError("root", { message: errorMessage(e) });
              }
            })}
          >
            <Input
              label="E-mail"
              autoComplete="username"
              {...register("email")}
              error={errors.email?.message}
            />
            <Input
              label="Senha"
              type="password"
              autoComplete="current-password"
              {...register("password")}
              error={errors.password?.message}
            />
            {errors.root && (
              <p role="alert" className="text-sm text-danger-700">
                {errors.root.message}
              </p>
            )}
            <Button type="submit" className="w-full" loading={isSubmitting}>
              Entrar
            </Button>
          </form>
          <p className="mt-8 rounded-lg bg-ink-100 p-4 text-xs text-ink-600">
            Ambiente local: utilize uma conta de demonstração e a senha
            configurada no README do projeto.
          </p>
        </div>
      </section>
    </main>
  );
}
