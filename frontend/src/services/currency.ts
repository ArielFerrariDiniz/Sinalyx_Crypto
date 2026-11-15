import { decimal } from './format';

export type DisplayCurrency = 'USD' | 'BRL';

function parseDecimal(value: string): { coefficient: bigint; scale: number } | null {
  if (value.length > 4096) return null;
  const match = /^([+-]?)(?:(\d+)(?:\.(\d*))?|\.(\d+))(?:e([+-]?\d+))?$/i.exec(value.trim());
  if (!match) return null;

  const exponent = Number(match[5] ?? '0');
  if (!Number.isSafeInteger(exponent) || Math.abs(exponent) > 1000) return null;
  const integer = match[2] ?? '0';
  const fraction = match[3] ?? match[4] ?? '';
  const digits = `${integer}${fraction}`;
  let coefficient = BigInt(digits || '0');
  if (match[1] === '-') coefficient = -coefficient;

  let scale = fraction.length - exponent;
  if (scale < 0) {
    coefficient *= 10n ** BigInt(-scale);
    scale = 0;
  }
  return { coefficient, scale };
}

/** Multiplicação decimal exata com arredondamento comercial para a precisão exibida. */
export function multiplyDecimalStrings(left: string, right: string, fractionDigits: number): string | null {
  if (!Number.isInteger(fractionDigits) || fractionDigits < 0 || fractionDigits > 100) return null;
  const a = parseDecimal(left);
  const b = parseDecimal(right);
  if (!a || !b) return null;

  let product = a.coefficient * b.coefficient;
  const scale = a.scale + b.scale;
  if (scale > fractionDigits) {
    const divisor = 10n ** BigInt(scale - fractionDigits);
    const absolute = product < 0n ? -product : product;
    let rounded = absolute / divisor;
    if ((absolute % divisor) * 2n >= divisor) rounded += 1n;
    product = product < 0n ? -rounded : rounded;
  } else if (scale < fractionDigits) {
    product *= 10n ** BigInt(fractionDigits - scale);
  }

  const negative = product < 0n;
  const digits = (negative ? -product : product).toString().padStart(fractionDigits + 1, '0');
  const value = fractionDigits === 0
    ? digits
    : `${digits.slice(0, -fractionDigits)}.${digits.slice(-fractionDigits)}`;
  return `${negative ? '-' : ''}${value}`;
}

export function formatMoney(value: string, currency: DisplayCurrency, usdtBrlRate: string | null, fractionDigits: number): string | null {
  if (currency === 'USD') return formatSignedDecimal(value, fractionDigits);
  if (usdtBrlRate === null) return null;

  const converted = multiplyDecimalStrings(value, usdtBrlRate, fractionDigits);
  if (converted === null) return null;
  const negative = converted.startsWith('-');
  const amount = negative ? converted.slice(1) : converted;
  return `${negative ? '−' : ''}R$ ${decimal(amount, fractionDigits)}`;
}

function formatSignedDecimal(value: string, fractionDigits: number): string | null {
  const negative = value.trim().startsWith('-');
  const amount = negative ? value.trim().slice(1) : value;
  if (!/^(?:\d+(?:\.\d*)?|\.\d+)(?:e[+-]?\d+)?$/i.test(amount)) return null;
  return `${negative ? '−' : ''}${decimal(amount, fractionDigits)}`;
}
