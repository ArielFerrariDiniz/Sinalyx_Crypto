import { useState, type FormEvent } from 'react';
import { Spinner } from './Spinner';

interface Props {
  busy: boolean;
  onConnect: (apiKey: string, secretKey: string) => Promise<void>;
}

export function ConnectionForm({ busy, onConnect }: Props) {
  const [apiKey, setApiKey] = useState('');
  const [secretKey, setSecretKey] = useState('');
  const [showSecret, setShowSecret] = useState(false);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (busy) return;
    const pending = onConnect(apiKey, secretKey);
    // Limpa imediatamente os campos; nenhum segredo fica no estado após envio.
    setApiKey(''); setSecretKey(''); setShowSecret(false);
    await pending;
  }

  return (
    <form onSubmit={submit} className="connection-form" autoComplete="off" aria-busy={busy}>
      <label htmlFor="api-key">API Key</label>
      <input id="api-key" name="api-key" type="password" autoComplete="off" spellCheck={false}
        autoCapitalize="none" value={apiKey} onChange={event => setApiKey(event.target.value)}
        placeholder="Informe sua API Key" required maxLength={256} disabled={busy} />
      <label htmlFor="secret-key">Secret Key</label>
      <div className="secret-field">
        <input id="secret-key" name="secret-key" type={showSecret ? 'text' : 'password'} autoComplete="off"
          spellCheck={false} autoCapitalize="none" value={secretKey} onChange={event => setSecretKey(event.target.value)}
          placeholder="Informe sua Secret Key" required maxLength={256} disabled={busy} />
        <button type="button" className="reveal" aria-label={showSecret ? 'Ocultar Secret Key' : 'Mostrar Secret Key'}
          aria-pressed={showSecret} onClick={() => setShowSecret(!showSecret)} disabled={busy}>
          {showSecret ? 'Ocultar' : 'Mostrar'}
        </button>
      </div>
      <p className="field-help">Use uma chave HMAC exclusiva, apenas com permissão de leitura.</p>
      <button type="submit" className="button button-primary connect-button" disabled={busy || !apiKey || !secretKey}>
        {busy ? <><Spinner /> Validando conexão…</> : <>Conectar Binance <span aria-hidden="true">↗</span></>}
      </button>
      <p className="form-footnote">Suas chaves são enviadas somente ao backend local e ficam salvas no cofre seguro do Linux, não no navegador.</p>
    </form>
  );
}
