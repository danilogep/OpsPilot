import { useState } from "react";
import {
  NavLink,
  Navigate,
  Outlet,
  Route,
  Routes,
  useLocation,
} from "react-router-dom";
import { useQueryClient } from "@tanstack/react-query";
import { useAuth } from "@/lib/auth";
import { Button } from "@/components/ui/Button";
import { LoadingState } from "@/components/ui/States";
import { roleLabels } from "@/lib/labels";
import { Login } from "@/routes/Login";
import { Dashboard } from "@/routes/Dashboard";
import { Imports, ImportDetail } from "@/routes/Imports";
import {
  Customers,
  CustomerDetail,
  Leads,
  LeadDetail,
  Renewals,
  Plans,
} from "@/routes/Crm";
import { Knowledge, Assistant, Agents } from "@/routes/Intelligence";
import { Integrations, Audit, Settings } from "@/routes/Administration";

const links = [
  ["/", "Visão geral", "◈"],
  ["/imports", "Importações", "↥"],
  ["/customers", "Clientes", "◎"],
  ["/leads", "Leads", "↗"],
  ["/renewals", "Renovações", "◷"],
  ["/plans", "Planos", "▤"],
  ["/knowledge", "Conhecimento", "▧"],
  ["/assistant", "Assistente de IA", "✧"],
  ["/agents", "Agentes", "⌘"],
  ["/integrations", "Integrações", "⇄"],
  ["/audit", "Auditoria", "≡"],
  ["/settings", "Configurações", "⚙"],
];

function Layout() {
  const auth = useAuth();
  const location = useLocation();
  const client = useQueryClient();
  const [open, setOpen] = useState(false);
  if (auth.isLoading) return <LoadingState label="Verificando sua sessão…" />;
  if (!auth.isAuthenticated)
    return <Navigate to="/login" state={{ from: location.pathname }} replace />;
  return (
    <div className="min-h-screen lg:flex">
      <aside className="border-r border-ink-200 bg-white lg:fixed lg:inset-y-0 lg:w-60 lg:overflow-y-auto">
        <div className="flex items-center justify-between px-6 py-6">
          <NavLink
            to="/"
            className="flex items-center gap-3 text-xl font-bold tracking-tight"
          >
            <span className="rounded-xl bg-brand-700 px-2.5 py-1 text-white">
              O
            </span>
            OpsPilot<span className="text-brand-600">.</span>
          </NavLink>
          <Button
            variant="ghost"
            className="lg:hidden"
            aria-label="Abrir navegação"
            aria-expanded={open}
            onClick={() => setOpen(!open)}
          >
            ☰
          </Button>
        </div>
        <nav
          aria-label="Navegação principal"
          className={`${open ? "block" : "hidden"} space-y-1 px-3 pb-5 lg:block`}
        >
          <p className="px-3 py-2 text-[10px] font-semibold uppercase tracking-[.18em] text-ink-400">
            Sua operação
          </p>
          {links.map(([path, label, icon]) => (
            <NavLink
              end={path === "/"}
              key={path}
              to={path}
              onClick={() => setOpen(false)}
              className={({ isActive }) =>
                `flex items-center gap-3 rounded-lg px-3 py-2.5 text-sm transition-colors ${isActive ? "bg-brand-50 font-semibold text-brand-800" : "text-ink-500 hover:bg-ink-50 hover:text-ink-900"}`
              }
            >
              <span aria-hidden="true" className="w-5 text-center text-lg">
                {icon}
              </span>
              {label}
            </NavLink>
          ))}
        </nav>
        <div className="m-4 hidden rounded-xl border border-brand-100 bg-brand-50 p-4 text-xs text-brand-800 lg:block">
          <strong>Ambiente de demonstração</strong>
          <p className="mt-1">
            Explore com dados sintéticos. Todas as ações ficam registradas.
          </p>
        </div>
      </aside>
      <div className="min-w-0 flex-1 lg:ml-60">
        <header className="flex flex-wrap items-center justify-between gap-3 border-b border-ink-200 bg-white px-5 py-4 lg:px-9">
          <span className="text-sm font-medium text-ink-600">
            {auth.organization?.name}
          </span>
          <div className="flex items-center gap-3">
            <span className="text-right text-xs">
              <strong className="block text-ink-800">
                {auth.user?.full_name}
              </strong>
              {auth.user && roleLabels[auth.user.role]}
            </span>
            <Button
              variant="ghost"
              size="sm"
              onClick={() => {
                auth.logout();
                client.clear();
              }}
            >
              Sair
            </Button>
          </div>
        </header>
        <main id="main" className="mx-auto max-w-[1600px] p-5 lg:p-9">
          <Outlet />
        </main>
      </div>
    </div>
  );
}

export function App() {
  return (
    <Routes>
      <Route path="/login" element={<Login />} />
      <Route element={<Layout />}>
        <Route index element={<Dashboard />} />
        <Route path="imports" element={<Imports />} />
        <Route path="imports/:id" element={<ImportDetail />} />
        <Route path="customers" element={<Customers />} />
        <Route path="customers/:id" element={<CustomerDetail />} />
        <Route path="leads" element={<Leads />} />
        <Route path="leads/:id" element={<LeadDetail />} />
        <Route path="renewals" element={<Renewals />} />
        <Route path="plans" element={<Plans />} />
        <Route path="knowledge" element={<Knowledge />} />
        <Route path="assistant" element={<Assistant />} />
        <Route path="agents" element={<Agents />} />
        <Route path="integrations" element={<Integrations />} />
        <Route path="audit" element={<Audit />} />
        <Route path="settings" element={<Settings />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Route>
    </Routes>
  );
}
