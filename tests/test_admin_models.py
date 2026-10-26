from oss_kbdb.admin_api import DatabaseConfig, KBCreate, app, database_url
from oss_kbdb.kb_defaults import default_embedding, default_enrichment

def test_database_config_defaults_to_isolated_schema_assignment():
    config=DatabaseConfig(url='postgresql://host/db')
    assert config.schema_name is None
    assert config.vector_dimensions == 384
    assert config.sslmode == 'require'


def test_control_plane_registers_onboarding_routes():
    routes = {(route.path, frozenset(route.methods or [])) for route in app.routes}
    assert ('/v1/tenants', frozenset({'POST'})) in routes
    assert ('/v1/tenants/{tenant_id}/activation/resend', frozenset({'POST'})) in routes
    assert ('/v1/auth/activate', frozenset({'POST'})) in routes
    assert ('/v1/admin/smtp', frozenset({'GET'})) in routes
    assert ('/v1/admin/smtp', frozenset({'POST'})) in routes


def test_database_url_composes_credentials_only_when_needed():
    assert database_url({'url': 'postgresql://db.example:5432/kb', 'credentials': {'username': 'app', 'password': 'safe word'}}) == 'postgresql://app:safe%20word@db.example:5432/kb'
    assert database_url({'url': 'postgresql://existing:secret@db.example/kb', 'credentials': {'username': 'other', 'password': 'other'}}) == 'postgresql://existing:secret@db.example/kb'


def test_kb_create_uses_default_profiles_when_advanced_configs_are_absent():
    body = KBCreate(slug='manual', name='Manual', s3={'url': 'https://s3.example'})
    assert body.database_mode == body.embedding_mode == body.enrichment_mode == 'default'
    assert body.database is body.embedding is body.enrichment is None


def test_default_models_are_local_and_deterministic_without_external_credentials(monkeypatch):
    for name in ('DEFAULT_EMBEDDING_PROVIDER', 'DEFAULT_EMBEDDING_MODEL', 'DEFAULT_ENRICHMENT_PROVIDER', 'DEFAULT_ENRICHMENT_MODEL'):
        monkeypatch.delenv(name, raising=False)
    embedding, enrichment = default_embedding(), default_enrichment()
    assert embedding['provider'] == 'local'
    assert embedding['model'] == 'sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2'
    assert enrichment['provider'] == 'deterministic'
