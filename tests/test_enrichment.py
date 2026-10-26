from oss_kbdb.domain.models import Chunk
from oss_kbdb.services.enrichment import DeterministicEnricher


def test_enrichment_keeps_source_separate_and_enriches_search_text():
    chunk = Chunk(ordinal=1, kind="chunk", parent_ordinal=0, heading_path=("Roaming", "Ativação"),
                  content="Ative o roaming antes de viajar para evitar indisponibilidade.")
    value = DeterministicEnricher().enrich(chunk)
    assert value.title == "Ativação"
    assert "Roaming > Ativação" in value.search_text
    assert value.summary in value.search_text
    assert value.prompt_version == "enrich-v1"
