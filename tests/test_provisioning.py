import pytest
from oss_kbdb.provisioning import provision_kb_database

def test_rejects_schema_outside_kb_namespace():
    with pytest.raises(ValueError):
        provision_kb_database('postgresql://invalid', 'public')
