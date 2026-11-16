import type { MarketAsset } from './api';

export type MarketSortKey = 'price_usdt' | 'change_percent_24h' | 'volume_usdt_24h';
export type SortDirection = 'asc' | 'desc';

function decimalParts(value: string): { sign: number; coefficient: bigint; scale: number } {
  const negative = value.startsWith('-');
  const unsigned = negative ? value.slice(1) : value;
  const [coefficientText, exponentText = '0'] = unsigned.toLowerCase().split('e');
  const [whole, fraction = ''] = coefficientText.split('.');
  let coefficient = BigInt((whole + fraction).replace(/^0+(?=\d)/, '') || '0');
  let scale = fraction.length - Number.parseInt(exponentText, 10);
  if (scale < 0) { coefficient *= 10n ** BigInt(-scale); scale = 0; }
  while (scale > 0 && coefficient > 0n && coefficient % 10n === 0n) {
    coefficient /= 10n;
    scale -= 1;
  }
  return { sign: coefficient === 0n ? 0 : negative ? -1 : 1, coefficient, scale };
}

function compareDecimalStrings(left: string, right: string): number {
  const a = decimalParts(left);
  const b = decimalParts(right);
  if (a.sign !== b.sign) return a.sign < b.sign ? -1 : 1;
  if (a.sign === 0) return 0;
  const commonScale = Math.max(a.scale, b.scale);
  const aScaled = a.coefficient * 10n ** BigInt(commonScale - a.scale);
  const bScaled = b.coefficient * 10n ** BigInt(commonScale - b.scale);
  if (aScaled === bScaled) return 0;
  return (aScaled < bScaled ? -1 : 1) * a.sign;
}

export function filterMarketAssets(assets: MarketAsset[], search: string, pairFilter: string): MarketAsset[] {
  const coinQuery = search.trim().toLocaleLowerCase();
  const pairQuery = pairFilter.trim().toLocaleLowerCase();
  return assets.filter(asset =>
    (!coinQuery || asset.symbol.toLocaleLowerCase().includes(coinQuery)) &&
    (!pairQuery || asset.pair.toLocaleLowerCase().includes(pairQuery)),
  );
}

export function sortMarketAssets(assets: MarketAsset[], key: MarketSortKey, direction: SortDirection): MarketAsset[] {
  const multiplier = direction === 'asc' ? 1 : -1;
  return [...assets].sort((left, right) => {
    const a = left[key];
    const b = right[key];
    if (a === null && b !== null) return 1;
    if (b === null && a !== null) return -1;
    if (a === null && b === null) return left.symbol.localeCompare(right.symbol) * multiplier;
    const comparison = compareDecimalStrings(a!, b!);
    if (comparison !== 0) return comparison * multiplier;
    return left.symbol.localeCompare(right.symbol) * multiplier;
  });
}

export function paginateMarketAssets<T>(assets: T[], page: number, pageSize: number): T[] {
  const safePage = Math.max(0, Math.floor(page));
  const safeSize = Math.max(1, Math.floor(pageSize));
  return assets.slice(safePage * safeSize, (safePage + 1) * safeSize);
}
