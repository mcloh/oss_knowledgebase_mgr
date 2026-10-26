from oss_kbdb.admin_api import DatabaseConfig, app, database_url

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
