import type { MarketCandle } from './api';

export function mergeCandles(existing: MarketCandle[], incoming: MarketCandle[]): MarketCandle[] {
  const byOpenTime = new Map<number, MarketCandle>();
  for (const candle of existing) byOpenTime.set(candle.open_time, candle);
  for (const candle of incoming) byOpenTime.set(candle.open_time, candle);
  return [...byOpenTime.values()].sort((left, right) => left.open_time - right.open_time);
}

export function hasNewOlderCandles(existing: MarketCandle[], incoming: MarketCandle[]): boolean {
  if (existing.length === 0) return incoming.length > 0;
  const oldest = existing[0].open_time;
  return incoming.some(candle => candle.open_time < oldest);
}
