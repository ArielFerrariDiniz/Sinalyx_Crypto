export interface Asset {
  asset: string;
  free: string;
  locked: string;
  total: string;
  price_usdt: string | null;
  value_usdt: string | null;
  conversion_path: string[] | null;
}

export interface Portfolio {
  assets: Asset[];
  total_usdt: string;
  asset_count: number;
  unpriced_assets: string[];
  is_partial: boolean;
  updated_at: string;
  warnings: string[];
}

export class ApiError extends Error {
  constructor(public code: string, message: string) { super(message); }
}

export interface LocalSession { connected: boolean; warnings: string[] }

const BASE_URL = 'http://127.0.0.1:8000/api';

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${BASE_URL}${path}`, {
      ...init, credentials: 'include', cache: 'no-store',
      signal: AbortSignal.timeout(60_000),
    });
  } catch {
    throw new ApiError('local_connection', 'Não foi possível comunicar com o backend local. Verifique se ele está ativo em 127.0.0.1:8000 e tente novamente.');
  }
  if (!response.ok) {
    const error = await response.json().catch(() => null);
    throw new ApiError(error?.code ?? 'request_error', error?.message ?? 'Não foi possível concluir a consulta. Tente novamente.');
  }
  if (response.status === 204) return undefined as T;
  return response.json() as Promise<T>;
}

export const api = {
  session: () => request<LocalSession>('/session'),
  unlockVault: () => request<{ message: string }>('/vault/unlock', { method: 'POST' }),
  connect: (apiKey: string, secretKey: string) => request<{ message: string; warnings: string[] }>('/connect', {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ api_key: apiKey, secret_key: secretKey }),
  }),
  portfolio: () => request<Portfolio>('/portfolio'),
  disconnect: () => request<void>('/session', { method: 'DELETE' }),
};
