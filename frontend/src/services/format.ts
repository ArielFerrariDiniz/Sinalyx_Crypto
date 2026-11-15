// Formatação por strings/BigInt: nenhuma quantidade monetária passa por Number.
export function decimal(value: string, digits?: number): string {
  const [coefficient, exponentText = '0'] = value.toLowerCase().split('e');
  const [integer, fraction = ''] = coefficient.split('.');
  const raw = integer + fraction;
  const position = integer.length + parseInt(exponentText, 10);
  let whole: string;
  let part: string;
  if (position <= 0) {
    whole = '0'; part = '0'.repeat(-position) + raw;
  } else if (position >= raw.length) {
    whole = raw + '0'.repeat(position - raw.length); part = '';
  } else {
    whole = raw.slice(0, position); part = raw.slice(position);
  }
  whole = whole.replace(/^0+(?=\d)/, '');
  if (digits !== undefined) {
    const kept = part.padEnd(digits, '0').slice(0, digits);
    let scaled = BigInt(whole + kept);
    if (part.length > digits && part[digits] >= '5') scaled += 1n;
    const rounded = scaled.toString().padStart(digits + 1, '0');
    if (scaled === 0n && /[1-9]/.test(whole + part)) {
      return `< 0,${'0'.repeat(digits - 1)}1`;
    }
    whole = digits ? rounded.slice(0, -digits) : rounded;
    part = digits ? rounded.slice(-digits) : '';
  } else {
    part = part.replace(/0+$/, '');
  }
  return whole.replace(/\B(?=(\d{3})+(?!\d))/g, '.') + (part ? `,${part}` : '');
}

export function updatedTime(value: string): string {
  return new Intl.DateTimeFormat('pt-BR', {
    day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit', second: '2-digit',
  }).format(new Date(value));
}
