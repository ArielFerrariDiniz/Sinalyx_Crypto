export const FINANCIAL_MASK = '••••••';
export const PRIVACY_PREFERENCE_KEY = 'sinalyx.hideFinancialValues';

type PreferenceStorage = Pick<Storage, 'getItem' | 'setItem'>;

function browserStorage(): PreferenceStorage | undefined {
  try {
    return typeof window === 'undefined' ? undefined : window.localStorage;
  } catch {
    return undefined;
  }
}

export function readPrivacyPreference(storage?: PreferenceStorage): boolean {
  try {
    return (storage ?? browserStorage())?.getItem(PRIVACY_PREFERENCE_KEY) === 'true';
  } catch {
    return false;
  }
}

export function savePrivacyPreference(hidden: boolean, storage?: PreferenceStorage): void {
  try {
    (storage ?? browserStorage())?.setItem(PRIVACY_PREFERENCE_KEY, hidden ? 'true' : 'false');
  } catch {
    // A preferência é apenas visual; o dashboard continua disponível sem armazenamento local.
  }
}

export function financialValue(value: string, hidden: boolean): string {
  return hidden ? FINANCIAL_MASK : value;
}
