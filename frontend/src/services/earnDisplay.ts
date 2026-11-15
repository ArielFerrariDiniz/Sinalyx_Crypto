import type { AssetSource } from './api';

export interface EarnDisplayValues {
  apr: string;
  yesterday: string;
  cumulativeRewards: string;
}

function valueForLabel(lines: string[], label: string): string {
  const prefix = `${label}:`;
  const line = lines.find(item => item.startsWith(prefix));
  if (!line) return '—';

  const value = line.slice(prefix.length).replace(/\s+\(informativo(?:; não somado)?\)$/i, '').trim();
  return value || '—';
}

export function isEarnSource(source: Pick<AssetSource, 'wallet_id' | 'wallet'>): boolean {
  return /earn|yield|staking|bfusd|rwusd/i.test(`${source.wallet_id} ${source.wallet}`);
}

export function earnDisplayValues(source: Pick<AssetSource, 'position_details' | 'reward_notes'>): EarnDisplayValues {
  return {
    apr: valueForLabel(source.position_details, 'APR atual'),
    yesterday: valueForLabel(source.reward_notes, 'Rendimento de ontem'),
    cumulativeRewards: valueForLabel(source.reward_notes, 'Recompensas acumuladas'),
  };
}
