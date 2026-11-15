import asyncio
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.middleware.trustedhost import TrustedHostMiddleware

from .binance_client import BinanceClient, BinanceError
from .models import Credentials, Portfolio
from .services.vault import SecretServiceVault, VaultError
from .services.portfolio import collect_portfolio
from .services.sessions import SessionLimitReached, SessionNotFound, SessionStore

FRONTEND_ORIGIN = "http://127.0.0.1:5173"
COOKIE_NAME = "crypto_session"


def clear_cookie(response: Response):
    response.delete_cookie(COOKIE_NAME, path="/api", httponly=True, samesite="strict")


def create_app(binance: BinanceClient | None = None, sessions: SessionStore | None = None, vault=None) -> FastAPI:
    store = sessions if sessions is not None else SessionStore()
    credential_vault = vault if vault is not None else SecretServiceVault()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        # Sem proxies de ambiente nem redirecionamento que possam receber chaves.
        async with httpx.AsyncClient(
            base_url="https://api.binance.com", timeout=httpx.Timeout(10),
            trust_env=False, follow_redirects=False,
        ) as http:
            app.state.binance = binance if binance is not None else BinanceClient(http)
            try:
                yield
            finally:
                store.clear()

    app = FastAPI(title="Crypto Trading Bot", lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)
    app.state.sessions = store
    app.state.vault = credential_vault
    app.state.binance = binance
    # Serializa consultas: impede sobreposição de refresh/conexão no processo local.
    request_lock = asyncio.Lock()

    @app.middleware("http")
    async def local_security(request: Request, call_next):
        if request.client is None or request.client.host != "127.0.0.1":
            return JSONResponse({"code": "local_only", "message": "Aplicação disponível somente nesta máquina."}, status_code=403)
        if request.url.path.startswith("/api/") and request.method != "OPTIONS":
            if request.headers.get("origin") != FRONTEND_ORIGIN:
                return JSONResponse({"code": "origin_denied", "message": "Origem local não autorizada."}, status_code=403)
            if request.method == "POST":
                try:
                    if int(request.headers.get("content-length", "0")) > 4096:
                        return JSONResponse({"code": "invalid_request", "message": "Requisição muito grande."}, status_code=413)
                except ValueError:
                    return JSONResponse({"code": "invalid_request", "message": "Requisição inválida."}, status_code=400)
        try:
            response = await call_next(request)
        except Exception:
            # Não encaminhar corpo/headers/exceções com credenciais para logs.
            response = JSONResponse({"code": "internal_error", "message": "Erro interno ao consultar a carteira. Tente novamente."}, status_code=500)
        response.headers["Cache-Control"] = "no-store"
        response.headers["Pragma"] = "no-cache"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        return response
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=["127.0.0.1"])
    app.add_middleware(
        CORSMiddleware, allow_origins=[FRONTEND_ORIGIN], allow_credentials=True,
        allow_methods=["GET", "POST", "DELETE"], allow_headers=["Content-Type"],
    )

    @app.exception_handler(RequestValidationError)
    async def validation_error(_request, _error):
        # O handler padrão do FastAPI inclui o input inválido: nunca usá-lo aqui.
        return JSONResponse({"code": "invalid_request", "message": "Confira os campos informados. Chaves HMAC não devem conter espaços."}, status_code=422)

    @app.exception_handler(VaultError)
    async def vault_error(_request, error):
        return JSONResponse({"code": error.code, "message": error.message}, status_code=503)

    @app.exception_handler(BinanceError)
    async def binance_error(_request, error):
        headers = {"Retry-After": str(error.retry_after)} if error.retry_after else None
        return JSONResponse({"code": error.code, "message": error.message}, status_code=error.status, headers=headers)

    @app.exception_handler(SessionNotFound)
    async def session_error(_request, _error):
        response = JSONResponse({"code": "session_missing", "message": "Sessão local encerrada. Atualize a página para restaurá-la do cofre seguro."}, status_code=401)
        clear_cookie(response)
        return response

    @app.exception_handler(SessionLimitReached)
    async def session_limit(_request, _error):
        return JSONResponse({"code": "session_limit", "message": "Limite de sessões locais atingido. Desconecte uma sessão existente antes de conectar novamente."}, status_code=409)

    @app.get("/api/session")
    async def current_session(request: Request, response: Response):
        token = request.cookies.get(COOKIE_NAME)
        try:
            session = store.require(token)
        except SessionNotFound:
            # Cookie de sessão novo, perdido ou emitido por um backend anterior:
            # reidrate a sessão das credenciais armazenadas no cofre do sistema.
            async with request_lock:
                try:
                    session = store.require(token)
                except SessionNotFound:
                    try:
                        credentials = await asyncio.to_thread(credential_vault.read)
                        warnings = await request.app.state.binance.permission_warnings(credentials) if credentials else []
                    except VaultError as error:
                        if error.code != "vault_invalid":
                            raise
                        credentials, warnings = None, [error.message]
                    session = set_session(response, request, credentials, warnings)
        return {"warnings": session.warnings.copy(), "connected": session.credentials is not None}

    @app.post("/api/vault/unlock")
    async def unlock_vault():
        async with request_lock:
            await asyncio.to_thread(credential_vault.unlock)
        return {"message": "Cofre do Linux desbloqueado."}

    def set_session(response: Response, request: Request, credentials, warnings):
        store.delete(request.cookies.get(COOKIE_NAME))
        token = store.create(credentials, warnings)
        response.set_cookie(COOKIE_NAME, token, httponly=True, samesite="strict", path="/api", secure=False)
        return store.require(token)

    @app.post("/api/connect")
    async def connect(credentials: Credentials, request: Request, response: Response):
        async with request_lock:
            store.require(request.cookies.get(COOKIE_NAME))
            client = request.app.state.binance
            await client.account(credentials)
            warnings = await client.permission_warnings(credentials)
            await asyncio.to_thread(credential_vault.write, credentials)
            store.update_credentials(credentials, warnings)
            set_session(response, request, credentials, warnings)
        return {"message": "Conexão com a Binance validada.", "warnings": warnings}

    @app.get("/api/portfolio", response_model=Portfolio)
    async def portfolio(request: Request):
        async with request_lock:
            token = request.cookies.get(COOKIE_NAME)
            session = store.require(token)
            credentials = session.credentials
            if credentials is None:
                return JSONResponse({"code": "not_connected", "message": "Conecte sua conta Binance para consultar a carteira."}, status_code=409)
            client = request.app.state.binance
            portfolio = await collect_portfolio(client, credentials, session.warnings.copy())
            # Uma desconexão durante o GET não pode devolver dados.
            store.require(token)
            return portfolio

    @app.delete("/api/session", status_code=204)
    async def disconnect(request: Request):
        async with request_lock:
            store.require(request.cookies.get(COOKIE_NAME))
            try:
                await asyncio.to_thread(credential_vault.delete)
            finally:
                store.clear()
        response = Response(status_code=204)
        clear_cookie(response)
        return response

    return app


app = create_app()
