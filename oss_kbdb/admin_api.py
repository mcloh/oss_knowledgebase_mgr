"""API administrativa e de serving multi-tenant do OSS-KBDB."""
from __future__ import annotations

import hashlib
import json
import os
import re
import secrets
import smtplib
import time
from email.message import EmailMessage
from typing import Literal

import jwt
from argon2 import PasswordHasher
from cryptography.fernet import Fernet
from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, Field

from oss_kbdb.adapters.embeddings import LocalEmbedder, OpenAICompatibleEmbedder
from oss_kbdb.adapters.postgres import PostgresRepository
from oss_kbdb.config import Settings
from oss_kbdb.kb_defaults import database_url, default_chunk_config, default_database, default_embedding, default_enrichment
from oss_kbdb.provisioning import provision_kb_database

app = FastAPI(title="OSS-KBDB Control Plane", version="0.1.1")
bearer = HTTPBearer()
ph = PasswordHasher()
app.add_middleware(
    CORSMiddleware,
    allow_origins=[os.getenv("ADMIN_ORIGIN", "https://osskbdb.xptoai.com.br")],
    allow_credentials=True, allow_methods=["GET", "POST"],
    allow_headers=["Authorization", "Content-Type", "X-API-Key"],
)


def db() -> PostgresRepository:
    return PostgresRepository(Settings.from_env().database_url)


def crypto() -> Fernet:
    return Fernet(os.environ["CONTROL_PLANE_FERNET_KEY"].encode())


def token(user: dict) -> str:
    return jwt.encode(
        {"sub": str(user["id"]), "role": user["role"],
         "tenant_id": str(user["tenant_id"]) if user["tenant_id"] else None,
         "exp": time.time() + 3600},
        os.environ["CONTROL_PLANE_JWT_SECRET"], algorithm="HS256",
    )


def actor(c: HTTPAuthorizationCredentials = Depends(bearer)) -> dict:
    try:
        return jwt.decode(c.credentials, os.environ["CONTROL_PLANE_JWT_SECRET"], algorithms=["HS256"])
    except jwt.PyJWTError as exc:
        raise HTTPException(401, "token inválido") from exc


def require_admin(me: dict) -> None:
    if me["role"] != "admin":
        raise HTTPException(403, "admin necessário")


def decrypt(value: bytes) -> dict:
    return json.loads(crypto().decrypt(value).decode())


class Login(BaseModel):
    email: str
    password: str


class TenantCreate(BaseModel):
    slug: str = Field(pattern=r"^[a-z0-9-]{2,50}$")
    name: str = Field(min_length=2, max_length=160)
    admin_email: str


class Activate(BaseModel):
    token: str
    password: str


class SMTPConfig(BaseModel):
    host: str = Field(min_length=1)
    port: int = Field(default=465, ge=1, le=65535)
    username: str = Field(min_length=1)
    password: str | None = None
    sender: str = Field(min_length=3)


class Provider(BaseModel):
    url: str
    credentials: dict[str, str] = Field(default_factory=dict)
    model: str | None = None
    provider: Literal["local", "openai_compatible"] = "openai_compatible"
    dimensions: int = 384


class DatabaseConfig(BaseModel):
    url: str
    credentials: dict[str, str] = Field(default_factory=dict)
    schema_name: str | None = None
    vector_dimensions: int = 384
    sslmode: Literal["require", "verify-ca", "verify-full"] = "require"


class KBCreate(BaseModel):
    tenant_id: str | None = None
    slug: str
    name: str
    database_mode: Literal["default", "custom"] = "default"
    embedding_mode: Literal["default", "custom"] = "default"
    enrichment_mode: Literal["default", "custom"] = "default"
    database: DatabaseConfig | None = None
    s3: Provider
    embedding: Provider | None = None
    enrichment: Provider | None = None
    chunk_config: dict | None = None
    webhook_url: str | None = None
    webhook_secret: str | None = None


class KeyCreate(BaseModel):
    client_name: str
    scopes: list[str] = ["serve"]


class SearchRequest(BaseModel):
    query: str
    mode: Literal["lexical", "semantic", "hybrid"] = "hybrid"
    document_type: str | None = None
    limit: int = 10


@app.get("/v1/health")
def health():
    return {"status": "ok"}


@app.post("/v1/auth/login")
def login(body: Login):
    r = db()
    try:
        user = r._conn.execute(
            "SELECT id,tenant_id,role,password_hash,active FROM users WHERE email=%s", (body.email.lower(),)
        ).fetchone()
        if not user or not user[4]:
            raise HTTPException(401, "credenciais inválidas")
        try:
            ph.verify(user[3], body.password)
        except Exception as exc:
            raise HTTPException(401, "credenciais inválidas") from exc
        return {"access_token": token({"id": user[0], "tenant_id": user[1], "role": user[2]}), "token_type": "bearer"}
    finally:
        r.close()


def smtp_config(r: PostgresRepository) -> dict | None:
    row = r._conn.execute("SELECT value_ciphertext FROM system_settings WHERE setting_key='smtp'").fetchone()
    if row:
        return decrypt(row[0])
    if os.getenv("SMTP_HOST"):
        return {"host": os.getenv("SMTP_HOST"), "port": int(os.getenv("SMTP_PORT", "465")),
                "username": os.getenv("SMTP_USER"), "password": os.getenv("SMTP_PASSWORD"),
                "sender": os.getenv("SMTP_FROM")}
    return None


def public_smtp(config: dict | None) -> dict:
    if not config:
        return {"configured": False}
    return {"configured": True, "host": config["host"], "port": config["port"],
            "username": config["username"], "sender": config["sender"]}


def send_activation(config: dict, email: str, raw_token: str) -> None:
    link = os.getenv("ACTIVATION_URL", "https://osskbdb.xptoai.com.br") + "?activate=" + raw_token
    msg = EmailMessage()
    msg["Subject"] = "Ative seu acesso ao OSS-KBDB"
    msg["From"] = config["sender"]
    msg["To"] = email
    msg.set_content(f"Ative sua conta e defina a senha: {link}\nO link expira em 24 horas.")
    with smtplib.SMTP_SSL(config["host"], int(config["port"]), timeout=20) as client:
        client.login(config["username"], config["password"])
        client.send_message(msg)


@app.get("/v1/admin/smtp")
def get_smtp(me: dict = Depends(actor)):
    require_admin(me)
    r = db()
    try:
        return public_smtp(smtp_config(r))
    finally:
        r.close()


@app.post("/v1/admin/smtp")
def set_smtp(body: SMTPConfig, me: dict = Depends(actor)):
    require_admin(me)
    r = db()
    try:
        previous = smtp_config(r) or {}
        config = body.model_dump()
        config["password"] = body.password or previous.get("password")
        if not config["password"]:
            raise HTTPException(422, "informe a senha SMTP")
        r._conn.execute(
            "INSERT INTO system_settings(setting_key,value_ciphertext,updated_at) VALUES('smtp',%s,now()) "
            "ON CONFLICT(setting_key) DO UPDATE SET value_ciphertext=EXCLUDED.value_ciphertext,updated_at=now()",
            (crypto().encrypt(json.dumps(config).encode()),),
        )
        r._conn.commit()
        return public_smtp(config)
    finally:
        r.close()


def issue_activation(r: PostgresRepository, user_id: str) -> str:
    raw = secrets.token_urlsafe(32)
    r._conn.execute("UPDATE activation_tokens SET used_at=now() WHERE user_id=%s AND used_at IS NULL", (user_id,))
    r._conn.execute(
        "INSERT INTO activation_tokens(user_id,token_hash,expires_at) VALUES(%s,%s,now()+interval '24 hours')",
        (user_id, hashlib.sha256(raw.encode()).hexdigest()),
    )
    return raw


@app.post("/v1/tenants")
def create_tenant(body: TenantCreate, me: dict = Depends(actor)):
    require_admin(me)
    r = db()
    try:
        config = smtp_config(r)
        if not config:
            raise HTTPException(503, "SMTP não configurado; tenant não criado")
        row = r._conn.execute("INSERT INTO tenants(slug,name) VALUES(%s,%s) RETURNING id,slug,name", (body.slug, body.name)).fetchone()
        user = r._conn.execute(
            "INSERT INTO users(tenant_id,email,password_hash,role,active) VALUES(%s,%s,%s,'tenant',true) RETURNING id",
            (row[0], body.admin_email.lower(), "!activation_pending!"),
        ).fetchone()
        raw = issue_activation(r, user[0])
        r._conn.commit()
        try:
            send_activation(config, body.admin_email.lower(), raw)
        except Exception as exc:
            raise HTTPException(502, "tenant criado, mas o e-mail falhou; reenvie a ativação") from exc
        return {"id": str(row[0]), "slug": row[1], "name": row[2], "activation_sent": True}
    finally:
        r.close()


@app.post("/v1/tenants/{tenant_id}/activation/resend")
def resend_activation(tenant_id: str, me: dict = Depends(actor)):
    require_admin(me)
    r = db()
    try:
        config = smtp_config(r)
        if not config:
            raise HTTPException(503, "SMTP não configurado")
        user = r._conn.execute("SELECT id,email FROM users WHERE tenant_id=%s AND role='tenant'", (tenant_id,)).fetchone()
        if not user:
            raise HTTPException(404, "administrador do tenant não encontrado")
        raw = issue_activation(r, user[0])
        r._conn.commit()
        try:
            send_activation(config, user[1], raw)
        except Exception as exc:
            raise HTTPException(502, "não foi possível enviar o e-mail") from exc
        return {"activation_sent": True}
    finally:
        r.close()


@app.post("/v1/auth/activate")
def activate(body: Activate):
    if len(body.password) < 16:
        raise HTTPException(422, "senha deve ter ao menos 16 caracteres")
    r = db()
    try:
        row = r._conn.execute(
            "SELECT u.id FROM activation_tokens a JOIN users u ON u.id=a.user_id "
            "WHERE a.token_hash=%s AND a.used_at IS NULL AND a.expires_at>now()",
            (hashlib.sha256(body.token.encode()).hexdigest(),),
        ).fetchone()
        if not row:
            raise HTTPException(400, "token inválido ou expirado")
        r._conn.execute("UPDATE users SET password_hash=%s WHERE id=%s", (ph.hash(body.password), row[0]))
        r._conn.execute("UPDATE activation_tokens SET used_at=now() WHERE user_id=%s AND used_at IS NULL", (row[0],))
        r._conn.commit()
        return {"activated": True}
    finally:
        r.close()


@app.get("/v1/tenants")
def list_tenants(me: dict = Depends(actor)):
    r = db()
    try:
        sql, args = ("SELECT id,slug,name,active,created_at FROM tenants", ()) if me["role"] == "admin" else (
            "SELECT id,slug,name,active,created_at FROM tenants WHERE id=%s", (me["tenant_id"],))
        return [{"id": str(x[0]), "slug": x[1], "name": x[2], "active": x[3], "created_at": x[4]} for x in r._conn.execute(sql, args).fetchall()]
    finally:
        r.close()


@app.get("/v1/knowledge-bases")
def list_kbs(me: dict = Depends(actor)):
    r = db()
    try:
        sql, args = ("SELECT id,tenant_id,slug,name,active,created_at FROM knowledge_bases", ()) if me["role"] == "admin" else (
            "SELECT id,tenant_id,slug,name,active,created_at FROM knowledge_bases WHERE tenant_id=%s", (me["tenant_id"],))
        return [{"id": str(x[0]), "tenant_id": str(x[1]), "slug": x[2], "name": x[3], "active": x[4], "created_at": x[5]} for x in r._conn.execute(sql, args).fetchall()]
    finally:
        r.close()


@app.post("/v1/knowledge-bases")
def create_kb(body: KBCreate, me: dict = Depends(actor)):
    tenant_id = body.tenant_id if me["role"] == "admin" else me["tenant_id"]
    if not tenant_id:
        raise HTTPException(422, "tenant obrigatório")
    r = db()
    try:
        tenant = r._conn.execute("SELECT id FROM tenants WHERE id=%s AND active=true", (tenant_id,)).fetchone()
        if not tenant:
            raise HTTPException(404, "tenant não encontrado")
        try:
            database = default_database() if body.database_mode == "default" else body.database
            embedding = default_embedding() if body.embedding_mode == "default" else body.embedding
            enrichment = default_enrichment() if body.enrichment_mode == "default" else body.enrichment
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc
        if not database or not embedding or not enrichment:
            raise HTTPException(422, "configuração custom exige os dados do componente selecionado")
        safe_slug = re.sub("[^a-z0-9_]+", "_", body.slug.lower()).strip("_")[:32]
        if not safe_slug:
            raise HTTPException(422, "slug inválido")
        schema_name = f"kb_{str(tenant_id).replace('-', '')[:12]}_{safe_slug}"
        if isinstance(database, dict):
            database["schema_name"] = schema_name
        else:
            database.schema_name = schema_name
        database_payload = database if isinstance(database, dict) else database.model_dump()
        embedding_payload = embedding if isinstance(embedding, dict) else embedding.model_dump()
        enrichment_payload = enrichment if isinstance(enrichment, dict) else enrichment.model_dump()
        chunks = default_chunk_config() | (body.chunk_config or {})
        f = crypto()
        row = r._conn.execute(
            """INSERT INTO knowledge_bases(tenant_id,slug,name,database_config_ciphertext,s3_config_ciphertext,
               embedding_config_ciphertext,enrichment_config_ciphertext,chunk_config,webhook_url,webhook_secret_ciphertext)
               VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id""",
            (tenant_id, body.slug, body.name, f.encrypt(json.dumps(database_payload).encode()),
             f.encrypt(body.s3.model_dump_json().encode()), f.encrypt(json.dumps(embedding_payload).encode()),
             f.encrypt(json.dumps(enrichment_payload).encode()), json.dumps(chunks), body.webhook_url,
             f.encrypt(body.webhook_secret.encode()) if body.webhook_secret else None),
        ).fetchone()
        r._conn.commit()
        return {"id": str(row[0]), "slug": body.slug, "schema": database_payload["schema_name"],
                "configuration": {"database": body.database_mode, "embedding": body.embedding_mode, "enrichment": body.enrichment_mode}}
    finally:
        r.close()


def kb_owned(r: PostgresRepository, kb_id: str, me: dict, fields: str = "tenant_id"):
    row = r._conn.execute(f"SELECT {fields} FROM knowledge_bases WHERE id=%s", (kb_id,)).fetchone()
    if not row or (me["role"] != "admin" and str(row[0]) != str(me["tenant_id"])):
        raise HTTPException(404, "KB não encontrada")
    return row


@app.post("/v1/knowledge-bases/{kb_id}/api-keys")
def create_key(kb_id: str, body: KeyCreate, me: dict = Depends(actor)):
    raw = "kb_" + secrets.token_urlsafe(32)
    r = db()
    try:
        kb = kb_owned(r, kb_id, me)
        row = r._conn.execute(
            "INSERT INTO api_keys(tenant_id,kb_id,client_name,key_prefix,key_hash,scopes) VALUES(%s,%s,%s,%s,%s,%s) RETURNING id",
            (kb[0], kb_id, body.client_name, raw[:12], hashlib.sha256(raw.encode()).hexdigest(), body.scopes),
        ).fetchone()
        r._conn.commit()
        return {"id": str(row[0]), "api_key": raw, "warning": "exibida somente uma vez"}
    finally:
        r.close()


@app.post("/v1/knowledge-bases/{kb_id}/provision")
def provision(kb_id: str, me: dict = Depends(actor)):
    r = db()
    try:
        row = kb_owned(r, kb_id, me, "tenant_id,database_config_ciphertext")
        cfg = decrypt(row[1])
        job = r._conn.execute("INSERT INTO jobs(tenant_id,kb_id,kind,status,payload) VALUES(%s,%s,'reindex','running','{}') RETURNING id", (row[0], kb_id)).fetchone()[0]
        r._conn.commit()
        try:
            provision_kb_database(database_url(cfg), cfg["schema_name"])
        except Exception as exc:
            r._conn.execute("UPDATE jobs SET status='failed',error=%s,finished_at=now() WHERE id=%s", (str(exc)[:1000], job))
            r._conn.commit()
            raise HTTPException(422, "provisionamento falhou; confira conexão, TLS e privilégios") from exc
        r._conn.execute("UPDATE jobs SET status='succeeded',finished_at=now() WHERE id=%s", (job,))
        r._conn.commit()
        return {"job_id": str(job), "status": "succeeded", "schema": cfg["schema_name"]}
    finally:
        r.close()


@app.post("/v1/knowledge-bases/{kb_id}/ingestion-jobs")
def enqueue_ingestion(kb_id: str, body: dict, me: dict = Depends(actor)):
    uri, document_type = body.get("source_uri"), body.get("document_type", "default")
    if not isinstance(uri, str) or not uri.startswith("s3://"):
        raise HTTPException(422, "source_uri s3:// obrigatório")
    r = db()
    try:
        kb = kb_owned(r, kb_id, me)
        row = r._conn.execute(
            "INSERT INTO jobs(tenant_id,kb_id,kind,status,payload) VALUES(%s,%s,'ingest','queued',%s) RETURNING id",
            (kb[0], kb_id, json.dumps({"source_uri": uri, "document_type": document_type})),
        ).fetchone()
        r._conn.commit()
        return {"job_id": str(row[0]), "status": "queued"}
    finally:
        r.close()


@app.get("/v1/metrics/usage")
def metrics(me: dict = Depends(actor)):
    r = db()
    try:
        where, args = ("", ()) if me["role"] == "admin" else ("WHERE tenant_id=%s", (me["tenant_id"],))
        rows = r._conn.execute(f"SELECT event_type,count(*),sum(units),avg(latency_ms) FROM usage_events {where} GROUP BY event_type", args).fetchall()
        return [{"event_type": x[0], "events": x[1], "units": x[2], "latency_ms": x[3]} for x in rows]
    finally:
        r.close()


def api_key(request: Request):
    raw = request.headers.get("x-api-key", "")
    if not raw.startswith("kb_"):
        raise HTTPException(401, "API key ausente")
    r = db()
    try:
        row = r._conn.execute("SELECT id,tenant_id,kb_id,scopes FROM api_keys WHERE key_hash=%s AND active=true", (hashlib.sha256(raw.encode()).hexdigest(),)).fetchone()
        if not row:
            raise HTTPException(401, "API key inválida")
        r._conn.execute("UPDATE api_keys SET last_used_at=now() WHERE id=%s", (row[0],))
        r._conn.commit()
        return {"id": row[0], "tenant_id": row[1], "kb_id": row[2], "scopes": row[3]}
    finally:
        r.close()


@app.post("/v1/serve/search")
def serve_search(body: SearchRequest, key: dict = Depends(api_key)):
    if "serve" not in key["scopes"]:
        raise HTTPException(403, "escopo serve necessário")
    started, control, data = time.perf_counter(), db(), None
    try:
        row = control._conn.execute(
            "SELECT database_config_ciphertext,embedding_config_ciphertext FROM knowledge_bases WHERE id=%s AND tenant_id=%s AND active=true",
            (key["kb_id"], key["tenant_id"]),
        ).fetchone()
        if not row:
            raise HTTPException(404, "KB indisponível")
        dbcfg, embcfg = decrypt(row[0]), decrypt(row[1])
        data = PostgresRepository(database_url(dbcfg), schema_name=dbcfg["schema_name"])
        vector = None
        if body.mode != "lexical":
            emb = LocalEmbedder(embcfg["model"], embcfg.get("dimensions", 384)) if embcfg.get("provider") == "local" else OpenAICompatibleEmbedder(embcfg["url"], embcfg.get("credentials", {}).get("api_key"), embcfg["model"], embcfg.get("dimensions", 384))
            vector = emb.embed([body.query])[0]
        hits = data.search(body.query, mode=body.mode, document_type=body.document_type, vector=vector, limit=min(body.limit, 50))
        expansion = data.expand([x.chunk_id for x in hits])
        latency = int((time.perf_counter() - started) * 1000)
        control._conn.execute("INSERT INTO usage_events(tenant_id,kb_id,api_key_id,event_type,latency_ms,metadata) VALUES(%s,%s,%s,'search',%s,%s)", (key["tenant_id"], key["kb_id"], key["id"], latency, json.dumps({"mode": body.mode, "result_count": len(hits)})))
        control._conn.commit()
        return {"results": [x.__dict__ | {"heading_path": list(x.heading_path), "expansion": expansion.get(x.chunk_id)} for x in hits], "latency_ms": latency}
    finally:
        if data:
            data.close()
        control.close()
