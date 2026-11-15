# Crypto Trading Bot — MVP 1

Aplicativo local para conectar uma API Key HMAC da Binance e consultar exclusivamente a carteira **Spot**. Mostra saldos disponíveis e bloqueados, cotações e patrimônio estimado em USDT, com atualização manual e desconexão.

Inicialização com um único comando e credenciais salvas somente no cofre Secret Service do Linux. Não há senha ou cadastro próprio do aplicativo nem expiração por inatividade. Ao abrir novamente, a carteira é restaurada automaticamente quando o cofre estiver acessível.

**Este MVP não executa ordens, compras, vendas, transferências ou saques.** Não contém estratégias, gráficos, banco de dados ou integração com outras exchanges. Futures, Margin, Earn e Funding não fazem parte da consulta.

## Requisitos

- Linux Debian 13, Python **3.13** com `venv` e Node.js **20.19+** (ou 22.12+), com npm.
- Acesso HTTPS à API da Binance e acesso à conta Binance para criar uma chave de leitura.
- Portas locais `8000` e `5173` disponíveis.
- Sessão gráfica Linux com D-Bus e um provedor Secret Service, como GNOME Keyring, com **cofre padrão persistente** configurado. O aplicativo não usa um cofre temporário nem fallback para arquivos.

Se necessário, instale os componentes Python do Debian:

```bash
sudo apt update
sudo apt install python3.13 python3.13-venv gnome-keyring seahorse xdg-utils
```

Confira as versões antes de continuar:

```bash
python3.13 --version
node --version
npm --version
```

Use sempre o diretório deste repositório como raiz; os comandos não criam outro projeto ou repositório.

## Instalar dependências

Na raiz do repositório:

```bash
python3.13 -m venv .venv
source .venv/bin/activate
python -m pip install -r backend/requirements.txt
```

Instale as dependências do frontend a partir da raiz:

```bash
npm ci --prefix frontend
```

O backend tem dependências fixadas em `requirements.txt`; o frontend usa `package-lock.json`. O `package.json` da raiz não precisa instalar pacotes: o inicializador usa somente módulos nativos do Node. Não há arquivo de credenciais ou variáveis de ambiente a preencher. Se a `.venv` já existir em `backend/.venv`, use `backend/.venv/bin/python -m pip install -r backend/requirements.txt`.

No GNOME, abra **Senhas e chaves / Seahorse** e confira se existe um cofre persistente definido como padrão. Configure e desbloqueie o cofre com a proteção nativa do GNOME Keyring. O aplicativo utiliza o Secret Service da sessão do seu usuário Linux; não execute com `sudo`. Em uma sessão sem interface gráfica, sem D-Bus ou sem provedor de cofre, o acesso fica bloqueado, com uma mensagem de erro. Não há armazenamento alternativo em texto simples.

## Iniciar a aplicação

Na raiz do repositório:

```bash
npm run dev
```

Abra **http://127.0.0.1:5173** ou, no terminal de `npm run dev`, pressione **o** e depois **Enter** para abrir esse endereço no navegador padrão. O atalho usa `xdg-open` (`xdg-utils` no Debian). Use o endereço exato: `localhost`, outro IP ou outra porta não são origens autorizadas pelo backend. O frontend fala apenas com `http://127.0.0.1:8000`; somente o backend envia as consultas autenticadas à Binance.

O inicializador encontra `.venv/bin/python` ou `backend/.venv/bin/python`, dando preferência ao ambiente da raiz. Verifica Python 3.13, dependências e disponibilidade das duas portas **antes de iniciar qualquer serviço**. Porta ocupada gera erro; o processo existente não é encerrado. O Vite também usa `--strictPort`. Os logs do FastAPI e Vite aparecem no mesmo terminal, identificados pelos prefixos `[backend]` e `[frontend]`. **Ctrl+C encerra os dois serviços e seus processos filhos**; fechar o terminal (SIGHUP) ou a falha de um serviço também encerra os dois.

Mantenha **um único processo/worker** do backend. Não use `--workers` nem `--reload`, não exponha o servidor na rede e não use este servidor de desenvolvimento como hospedagem pública. O inicializador não instala dependências, não muda configurações do Git e não configura inicialização automática no boot.

## Cofre seguro e restauração da conexão

1. Abra a aplicação. Se o cofre estiver bloqueado, clique em **Desbloquear cofre do Linux** e responda somente à **janela segura do sistema**. O aplicativo não recebe nem pede uma senha própria. Cancelar o desbloqueio mantém o acesso bloqueado.
2. Na primeira utilização, informe a API Key e a Secret Key de leitura e conecte. Após a validação bem-sucedida, o backend salva as chaves diretamente como um item secreto do cofre do Linux.
3. Nas próximas utilizações, inclusive depois de reiniciar o computador, execute `npm run dev`. O backend restaura as chaves do cofre e consulta a carteira automaticamente, sem senha própria do aplicativo e sem redigitar as chaves.
4. Fechar e reabrir a página, perder o cookie de sessão ou reiniciar o backend não exige novo login: a próxima consulta recria uma sessão temporária a partir do cofre. Nenhuma credencial é persistida no navegador.

A conexão permanece **configurada**, sem timeout por inatividade, até ser removida manualmente. A disponibilidade das consultas depende da rede, da Binance e da validade/permissão das chaves. O aplicativo consulta a carteira ao abrir e nas atualizações manuais, sem polling em segundo plano.

As credenciais salvas por uma versão anterior foram cifradas com uma senha própria do aplicativo que não era persistida. Não é possível migrar esse registro sem a senha antiga; nessa atualização, conecte novamente uma vez para substituí-lo por um item Secret Service. O registro antigo é removido ao salvar as novas credenciais ou ao desconectar.

## Criar a API Key de leitura

1. Acesse sua conta no **site oficial da Binance**, abra o perfil e procure **Gerenciamento de API / API Management**. A disponibilidade e os nomes dos controles podem variar por conta/região.
2. Crie uma chave **gerada pelo sistema / HMAC**, exclusiva para este aplicativo, e conclua as verificações de segurança solicitadas pela Binance. Chaves RSA/Ed25519 não são suportadas neste MVP.
3. Mantenha apenas **Habilitar leitura / Enable Reading**. Deixe trading Spot/Margin, Futures, opções, transferências e saques desabilitados. Não habilite trading para contornar um erro de leitura.
4. Se usar restrição de IP na Binance, autorize o **IP público de saída da sua conexão**, não `127.0.0.1`. Atualize a restrição se seu IP público mudar.
5. A Binance exibe a Secret Key no momento da criação. Use-a somente no formulário local; não a coloque em código, arquivos, terminal, capturas de tela, mensagens ou Git. Recuse a opção de salvar credenciais do navegador.

Referências oficiais: [criação de chaves](https://www.binance.com/en/support/faq/detail/360002502072), [segurança da REST API Spot e HMAC](https://developers.binance.com/docs/binance-spot-api-docs/rest-api), [consulta de permissões da API Key](https://developers.binance.com/docs/wallet/account/api-key-permission).

## Conectar e validar os saldos reais

1. Com `npm run dev` ativo, informe a API Key e a Secret Key. É possível mostrar/ocultar a Secret Key.
2. Clique em **Conectar Binance**. O backend valida as credenciais consultando `GET /api/v3/account`. Os campos são limpos após o envio. A interface só confirma a conexão se essa chamada autenticada tiver sucesso.
3. A carteira é consultada em seguida. Se a consulta dos preços falhar depois da autenticação, a sessão continua disponível para **Atualizar carteira** ou **Desconectar**. Confira os avisos sobre permissões excessivas ou impossibilidade de verificá-las.
4. No site/app da Binance, abra a carteira **Spot**, na mesma conta ou subconta da chave. Compare cada ativo: `disponível`, `bloqueado` e `total = disponível + bloqueado`. Ativos com apenas saldo bloqueado também aparecem; saldos zerados são omitidos.
5. Confira um ativo com par USDT e um ativo com conversão intermediária, se houver. A interface informa o intermediário utilizado. O USDT vale exatamente 1 USDT; outras stablecoins usam a cotação de mercado.
6. Compare o patrimônio apenas com o saldo **Spot**. A Binance pode incluir outras carteiras, usar outros preços de referência e arredondamentos. As chamadas de saldo e preço são sequenciais, portanto não formam um snapshot atômico.
7. Clique em **Atualizar carteira** para uma nova consulta e confira o horário exibido. Em falhas de atualização, os dados anteriores ficam identificados como a última consulta bem-sucedida; eles não são substituídos por zeros.
8. Clique em **Desconectar e remover credenciais**. O backend apaga os itens do aplicativo no cofre, limpa as credenciais em memória, invalida as sessões locais e remove o cookie. Para conectar novamente, informe as chaves Binance. Se o cofre estiver bloqueado ou indisponível, a remoção não é confirmada: desbloqueie-o pela janela do sistema e repita. Encerrar somente o backend limpa a memória, mas preserva as credenciais protegidas no cofre.

**Nenhuma conexão com credenciais reais foi validada durante o desenvolvimento.** Os testes usam exclusivamente dados fictícios, com rede bloqueada. A validação real deve ser feita por você no formulário local; não envie suas chaves no chat.

## Cálculo das cotações e patrimônio

- `saldo_total = saldo_livre + saldo_bloqueado`.
- `valor_usdt = saldo_total × cotacao_usdt`.
- Todos os cálculos do backend usam `Decimal` com contexto de 60 dígitos; valores financeiros são enviados como **strings JSON**. O frontend formata strings/`BigInt`, sem converter valores financeiros em `Number`.
- `GET /api/v3/exchangeInfo?permissions=SPOT` identifica dinamicamente as moedas de cada par. `GET /api/v3/ticker/price` fornece os últimos preços. Não existe uma lista fixa de ativos suportados.
- A conversão usa apenas pares com status `TRADING`, negociação Spot permitida e preço estritamente positivo. O par direto tem preferência. Na falta dele, usa-se o menor caminho disponível, com no máximo **três pares / dois intermediários**, incluindo pares invertidos. O critério desempata alfabeticamente e evita ciclos.
- Cotação sem caminho válido é **indisponível** (`null`), nunca um zero inventado. O ativo continua na tabela; o patrimônio fica identificado como **parcial**, com os símbolos excluídos. Se nenhum ativo tiver cotação, a interface mostra um traço no patrimônio.
- Os preços são estimativas baseadas no último negócio. O endpoint de preço não informa o horário desse negócio; status ativo e preço positivo não garantem liquidez ou preço recente. Não se consideram taxas, spread ou slippage. Não é uma cotação garantida para execução.
- Quantidades são exibidas sem perda dos dígitos recebidos; preços têm 8 casas e valores em USDT, 2 casas. Valores positivos menores que a precisão visual aparecem como `< 0,01` (ou o limite de preço correspondente). Passe o cursor sobre os números da tabela para ver o valor integral retornado.

## Segurança e ciclo da sessão

- API Key e Secret Key são guardadas somente como conteúdo secreto no Secret Service. A criptografia em repouso e o bloqueio/desbloqueio são responsabilidade do cofre persistente do Linux. A aplicação não cria senha própria, chave de cifragem fixa, arquivo de credenciais, arquivo `.env` ou banco de dados.
- A integração usa `SecretStorage` diretamente, sem backends alternativos ou fallback para arquivos. Os atributos e o rótulo público do item contêm somente identificação do aplicativo e UID; as chaves ficam no conteúdo secreto do cofre.
- As chaves recuperadas do cofre existem em memória no backend enquanto as consultas são feitas. Nenhuma Secret Key é devolvida pelo backend. A API Key vai no header `X-MBX-APIKEY`; a Secret Key serve apenas para calcular o HMAC e nunca entra na URL. Os campos do formulário são limpos após o envio; credenciais não são salvas em `localStorage`, `sessionStorage` ou cookies.
- Sessão opaca de 256 bits, guardada apenas em memória no backend. O navegador recebe somente um cookie **de sessão**, `HttpOnly`, `SameSite=Strict`, limitado a `/api`, sem `Expires` ou `Max-Age`. O cookie contém o identificador aleatório, não as chaves.
- O cookie usa HTTP local, portanto não tem `Secure`; o aplicativo depende do loopback e não é adequado para exposição pública. O backend rejeita clientes fora de `127.0.0.1`, Hosts diferentes e chamadas à API sem a origem exata do frontend. CORS permite somente `http://127.0.0.1:5173`, com credenciais.
- **Não existe expiração por inatividade** nem rotina de limpeza por tempo. Encerrar o backend invalida os identificadores de sessão e remove as referências às credenciais da RAM, preservando somente o item protegido no cofre. Python não oferece garantia de sobrescrita física de strings na memória.
- Quando a sessão de navegador está ausente ou foi perdida após reiniciar o backend, a rota local recupera as credenciais do cofre e emite um novo cookie temporário. O backend continua restrito a `127.0.0.1`, exige a origem exata do frontend e não oferece acesso remoto. A proteção da conta depende também do usuário Linux e do bloqueio nativo do cofre.
- Até 16 sessões locais são permitidas; atingir o limite recusa novas sessões sem desconectar as existentes.
- A proteção depende também da segurança da sessão Linux: processos com privilégios de root ou acesso ao mesmo usuário podem acessar memória ou interferir no navegador. Este aplicativo não oferece isolamento contra um sistema operacional comprometido.
- Não há logs de tráfego `httpx`/`httpcore`, `SecretStorage` ou `Jeepney`. Mensagens da Binance, corpo de validação e exceções inesperadas não são repassados ao navegador nem aos logs. Não ative captura de corpos/headers, depuradores ou logs detalhados contendo chaves.
- O cliente da Binance permite exclusivamente cinco endpoints GET: horário, conta Spot, preços, metadados dos pares e permissões da chave. Não segue redirecionamentos nem usa proxies de ambiente.
- A chave é inspecionada via `GET /sapi/v1/account/apiRestrictions`, quando disponível. Permissões de trading, saques ou transferências geram aviso. Se essa inspeção falhar, a conexão de leitura pode continuar, com aviso para conferir as permissões na Binance. Os campos `canTrade`/`canWithdraw` da conta não são tratados como permissões da chave.

## Tratamento de erros

A interface apresenta erros de chave inválida, assinatura/Secret Key, acesso/permissões/IP, rede, timeout, rate limit, sincronização e indisponibilidade. A Binance pode responder com o mesmo código `-2015` para chave inválida, IP bloqueado ou permissão insuficiente; o aplicativo informa essa ambiguidade. `-1022` indica assinatura inválida e recomenda verificar a Secret Key e o par de credenciais.

Antes das consultas assinadas, o backend sincroniza com `GET /api/v3/time`, compensando metade do tempo de ida e volta da consulta. Usa `recvWindow=5000` e uma única nova sincronização/tentativa para `-1021`. Respostas `418`/`429` respeitam `Retry-After` (60 segundos na ausência de um valor válido); novas consultas ao upstream ficam bloqueadas em memória durante esse intervalo. Não há repetição automática de outras falhas.

Se o backend não iniciar, confirme a ativação da `.venv`, a versão do Python e a disponibilidade da porta. Se houver erro de origem, abra o endereço com `127.0.0.1`, não `localhost`. Erros de assinatura exigem conferir ambas as chaves, sem habilitar permissões adicionais.

## Testes e build

Na raiz, para testar o inicializador (sem dependências Node adicionais):

```bash
npm test
```

Esses testes usam processos simulados, validando dependências ausentes, ambas as portas ocupadas, descoberta de `backend/.venv`, logs, Ctrl+C e encerramento quando um serviço falha. Precisam que as portas `8000` e `5173` estejam livres antes da execução.

Na raiz, com a `.venv` ativa:

```bash
python -m pytest -c backend/pytest.ini
```

A suíte usa `httpx.MockTransport`, cofre simulado e bloqueia conexões de rede. Cobre HMAC/headers/timestamp, falhas Binance, carteira e conversões, ausência de timeout por inatividade, restauração após reinício diretamente do cofre, cofre bloqueado/indisponível, exclusão e ausência de credenciais nas respostas/logs. Não utiliza chaves reais nem operações financeiras e não acessa o cofre pessoal.

O `TestClient` da versão fixada do Starlette emite um aviso de descontinuação para o transporte `httpx`; o transporte funciona e o aviso não representa uma falha dos testes. O cliente de produção continua usando `httpx`, conforme o escopo do MVP.

Para testar a formatação financeira, verificar TypeScript e gerar o frontend:

```bash
cd frontend
npm test
npm run build
```

Para testar o build localmente, pare o servidor Vite de desenvolvimento e execute `npm run preview`, também em `http://127.0.0.1:5173`. O backend deve continuar ativo. `frontend/dist` é gerado e ignorado pelo Git.

## Estrutura

```text
backend/
  app/
    __init__.py
    main.py                 # API local, proteção de origem e ciclo da aplicação
    binance_client.py       # GETs permitidos, HMAC, horário e erros
    models.py               # Validação e modelos Decimal
    services/
      __init__.py
      sessions.py           # Sessões em memória, sem timeout de inatividade
      vault.py              # Secret Service do Linux, sem fallback
      portfolio.py          # Conversões e patrimônio
  tests/
    conftest.py              # Binance simulada e bloqueio de rede
    test_api.py
    test_vault.py
  pytest.ini
  requirements.txt
frontend/
  src/
    components/
      ConnectionForm.tsx
      Notice.tsx
      PortfolioTable.tsx
      Spinner.tsx
    pages/
      ConnectPage.tsx
      PortfolioPage.tsx
      VaultAccessPage.tsx
    services/
      api.ts
      format.ts
    App.tsx
    main.tsx
    styles.css
  index.html
  package.json
  package-lock.json
  tsconfig.json
  vite.config.ts
  tests/
    format.test.mjs
README.md
.gitignore
package.json                # npm run dev e testes do inicializador
scripts/
  dev.mjs
tests/
  dev.test.mjs
```

## Encerrar

1. Use **Ctrl+C** no terminal de `npm run dev`. Frontend, backend e seus processos filhos são encerrados; a conexão permanece protegida no cofre para a próxima abertura.
2. Para esquecer a conexão, clique antes em **Desconectar e remover credenciais** e confirme a mensagem de remoção bem-sucedida.
3. Execute `deactivate` se tiver ativado a `.venv` para instalar dependências ou executar testes.

Não é necessário limpar pastas ou apagar arquivos para encerrar. Nenhuma funcionalidade de trading foi implementada.

## Git e arquivos sensíveis

O aplicativo não grava suas chaves no repositório. `.env`, ambientes virtuais, arquivos de chaves, cofres, exportações conhecidas e pastas de segredos estão no `.gitignore`. Não exporte o cofre para o projeto nem cole suas chaves em código, comandos ou mensagens. Os testes contêm apenas valores explicitamente fictícios.

A implementação não executa `git add`, `git commit` ou `git push`. Confira o conteúdo antes de versionar alterações. O `.gitignore` não remove segredos que já tenham sido rastreados anteriormente; se algum segredo real tiver sido exposto, revogue-o na Binance.

Referência de segurança: [SecretStorage e prompts do sistema](https://secretstorage.readthedocs.io/en/latest/).
