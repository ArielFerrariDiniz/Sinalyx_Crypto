export interface Asset {
  asset: string;
  free: string;
  locked: string;
  applied: string;
  liability: string;
  total: string;
  net_total: string;
  price_usdt: string | null;
  value_usdt: string | null;
  conversion_path: string[] | null;
  sources: AssetSource[];
}

export interface AssetSource {
  wallet_id: string;
  wallet: string;
  available: string;
  locked: string;
  applied: string;
  liability: string;
  total: string;
  net_total: string;
  reward_notes: string[];
  position_details: string[];
}

export interface WalletSummary {
  wallet_id: string;
  name: string;
  status: 'ok' | 'partial' | 'unavailable' | 'unsupported';
  asset_count: number;
  total_usdt: string | null;
  warning: string | null;
}

export interface Portfolio {
  assets: Asset[];
  wallets: WalletSummary[];
  total_usdt: string;
  asset_count: number;
  unpriced_assets: string[];
  is_partial: boolean;
  updated_at: string;
  usdt_brl_rate: string | null;
  usdt_brl_updated_at: string | null;
  usdt_brl_error: string | null;
  warnings: string[];
  coverage_notes: string[];
}

export interface MarketAsset {
  asset_id: string;
  symbol: string;
  pair: string;
  quote_asset: string;
  price_usdt: string | null;
  change_percent_24h: string | null;
  high_24h_usdt: string | null;
  low_24h_usdt: string | null;
  volume_usdt_24h: string | null;
  conversion_path: string[];
  conversion_approximate: boolean;
  open_time: number | null;
  close_time: number | null;
}

export interface MarketSnapshot {
  assets: MarketAsset[];
  updated_at: string;
}

export type MarketInterval = '1m' | '5m' | '15m' | '1h' | '4h' | '1d';

export interface MarketCandle {
  open_time: number;
  open: string;
  high: string;
  low: string;
  close: string;
  volume: string;
  close_time: number;
  quote_volume: string;
  trade_count: number;
}

export interface MarketCandlePage {
  pair: string;
  interval: MarketInterval;
  candles: MarketCandle[];
  earliest_open_time: number | null;
  oldest_open_time: number | null;
  latest_open_time: number | null;
  has_older: boolean;
  updated_at: string;
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
  market: (refresh = false) => request<MarketSnapshot>(`/market${refresh ? '?refresh=true' : ''}`),
  marketKlines: (pair: string, interval: MarketInterval, endTime?: number) => {
    const params = new URLSearchParams({ pair, interval });
    if (endTime !== undefined) params.set('end_time', String(endTime));
    return request<MarketCandlePage>(`/market/klines?${params.toString()}`);
  },
  disconnect: () => request<void>('/session', { method: 'DELETE' }),
};
