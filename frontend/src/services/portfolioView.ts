import type { Asset, Portfolio, WalletSummary } from './api';

function hasNonZeroAmount(value: string | null | undefined): boolean {
  if (value == null) return false;
  const normalized = value.trim().toLowerCase();
  if (!/^[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:e[+-]?\d+)?$/.test(normalized)) return false;
  const mantissa = normalized.split('e', 1)[0].replace(/[+-]/g, '');
  return /[1-9]/.test(mantissa);
}

export function filterWalletsWithBalance(wallets: WalletSummary[]): WalletSummary[] {
  // asset_count mantém visíveis saldos com cotação indisponível; total_usdt
  // cobre os subtotais agregados que não têm linhas por ativo.
  return wallets.filter(wallet => wallet.asset_count > 0 || hasNonZeroAmount(wallet.total_usdt));
}

export function filterAssetsWithBalance(assets: Asset[]): Asset[] {
  // Passivos e saldos líquidos Futures/Margin também são patrimônio ativo,
  // mesmo quando o total bruto do ativo é zero.
  return assets.filter(asset => hasNonZeroAmount(asset.total)
    || hasNonZeroAmount(asset.liability)
    || hasNonZeroAmount(asset.net_total));
}

export function splitAssetsByQuoteAvailability(assets: Asset[]): { priced: Asset[]; unpriced: Asset[] } {
  return {
    priced: assets.filter(asset => asset.price_usdt !== null),
    unpriced: assets.filter(asset => asset.price_usdt === null),
  };
}

export function buildQueryDetails(data: Portfolio | null, error: string, warnings: string[]): string[] {
  const details = new Set<string>();
  if (error.trim()) details.add(`A última consulta não foi concluída: ${error.trim()}`);
  for (const warning of warnings) if (warning.trim()) details.add(warning.trim());

  if (!data) return [...details];
  for (const warning of data.warnings) if (warning.trim()) details.add(warning.trim());
  for (const note of data.coverage_notes) if (note.trim()) details.add(note.trim());
  for (const wallet of data.wallets) {
    if (wallet.status !== 'ok') {
      details.add(`${wallet.name}: ${wallet.warning ?? statusDescription(wallet.status)}`);
    }
  }
  if (data.is_partial && !details.size) details.add('A estimativa do patrimônio está parcial.');
  return [...details];
}

export function emptyAssetsMessage(data: Portfolio, walletsWithBalance: WalletSummary[]): string {
  if (walletsWithBalance.length) {
    return 'Há modalidades com saldo detectado, mas nenhum ativo individual foi incluído nesta tabela. Consulte os detalhes da carteira.';
  }
  if (data.wallets.some(wallet => wallet.status !== 'ok')) {
    return 'Não foi possível confirmar saldo em todas as carteiras. Consulte os detalhes da consulta antes de concluir que estão vazias.';
  }
  return 'As carteiras consultadas não retornaram posições com saldo positivo.';
}

function statusDescription(status: WalletSummary['status']): string {
  if (status === 'partial') return 'Consulta incompleta.';
  if (status === 'unavailable') return 'Consulta indisponível; o saldo não foi confirmado.';
  if (status === 'unsupported') return 'Esta modalidade não é integrada.';
  return 'Consulta concluída.';
}
