/**
 * Sessão do usuário.
 *
 * O token fica em `localStorage` para sobreviver ao recarregamento da página e é
 * descartado automaticamente quando a API responde 401 (token expirado ou
 * inválido). Permissões são derivadas do papel, espelhando o backend.
 */

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";

import { api, readToken, UNAUTHORIZED_EVENT, writeToken } from "@/lib/api";
import type {
  LoginResponse,
  OrganizationSummary,
  User,
  UserRole,
} from "@/types/api";
import { useQueryClient } from "@tanstack/react-query";

const USER_STORAGE_KEY = "opspilot.user";
const ORG_STORAGE_KEY = "opspilot.organization";

export interface AuthState {
  user: User | null;
  organization: OrganizationSummary | null;
  isAuthenticated: boolean;
  isLoading: boolean;
  login: (email: string, password: string) => Promise<User>;
  logout: () => void;
  can: (permission: Permission) => boolean;
}

/** Permissões usadas pela interface (o backend é a fonte da verdade). */
export type Permission =
  | "data:write"
  | "imports:write"
  | "knowledge:write"
  | "assistant:write"
  | "users:manage"
  | "integrations:manage";

const PERMISSIONS_BY_ROLE: Record<UserRole, Permission[]> = {
  ADMIN: [
    "data:write",
    "imports:write",
    "knowledge:write",
    "assistant:write",
    "users:manage",
    "integrations:manage",
  ],
  ANALYST: [
    "data:write",
    "imports:write",
    "knowledge:write",
    "assistant:write",
  ],
  VIEWER: [],
};

const AuthContext = createContext<AuthState | null>(null);

function readStored<T>(key: string): T | null {
  try {
    const raw = window.localStorage.getItem(key);
    return raw ? (JSON.parse(raw) as T) : null;
  } catch {
    return null;
  }
}

function writeStored(key: string, value: unknown | null): void {
  try {
    if (value === null) window.localStorage.removeItem(key);
    else window.localStorage.setItem(key, JSON.stringify(value));
  } catch {
    /* sem storage disponível: sessão apenas em memória */
  }
}

export function AuthProvider({
  children,
}: {
  children: ReactNode;
}): JSX.Element {
  const queryClient = useQueryClient();
  const [user, setUser] = useState<User | null>(() =>
    readToken() ? readStored<User>(USER_STORAGE_KEY) : null,
  );
  const [organization, setOrganization] = useState<OrganizationSummary | null>(
    () => readStored<OrganizationSummary>(ORG_STORAGE_KEY),
  );
  const [isLoading, setIsLoading] = useState<boolean>(() =>
    Boolean(readToken()),
  );

  const clearSession = useCallback(() => {
    queryClient.clear();
    writeToken(null);
    writeStored(USER_STORAGE_KEY, null);
    writeStored(ORG_STORAGE_KEY, null);
    setUser(null);
    setOrganization(null);
    setIsLoading(false);
  }, [queryClient]);

  // Revalida o token guardado ao abrir a aplicação.
  useEffect(() => {
    const token = readToken();
    if (!token) {
      setIsLoading(false);
      return;
    }
    let active = true;
    void (async () => {
      try {
        const [currentUser, currentOrg] = await Promise.all([
          api.get<User>("/auth/me"),
          api.get<OrganizationSummary>("/auth/me/organization"),
        ]);
        if (!active) return;
        setUser(currentUser);
        setOrganization(currentOrg);
        writeStored(USER_STORAGE_KEY, currentUser);
        writeStored(ORG_STORAGE_KEY, currentOrg);
      } catch {
        if (active) clearSession();
      } finally {
        if (active) setIsLoading(false);
      }
    })();
    return () => {
      active = false;
    };
  }, [clearSession]);

  // Qualquer 401 da API encerra a sessão.
  useEffect(() => {
    const handler = (): void => clearSession();
    window.addEventListener(UNAUTHORIZED_EVENT, handler);
    return () => window.removeEventListener(UNAUTHORIZED_EVENT, handler);
  }, [clearSession]);

  const login = useCallback(
    async (email: string, password: string): Promise<User> => {
      const response = await api.post<LoginResponse>(
        "/auth/login",
        { email, password },
        undefined,
      );
      writeToken(response.access_token);
      queryClient.clear();
      writeStored(USER_STORAGE_KEY, response.user);
      writeStored(ORG_STORAGE_KEY, response.organization);
      setUser(response.user);
      setOrganization(response.organization);
      setIsLoading(false);
      return response.user;
    },
    [queryClient],
  );

  const value = useMemo<AuthState>(
    () => ({
      user,
      organization,
      isAuthenticated: Boolean(user),
      isLoading,
      login,
      logout: clearSession,
      can: (permission: Permission) =>
        Boolean(user && PERMISSIONS_BY_ROLE[user.role].includes(permission)),
    }),
    [user, organization, isLoading, login, clearSession],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthState {
  const context = useContext(AuthContext);
  if (!context)
    throw new Error("useAuth precisa estar dentro de AuthProvider.");
  return context;
}
