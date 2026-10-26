from oss_kbdb.services.chunker import hierarchical_chunks


def test_preserves_section_as_parent_and_children_inherit_path():
    text = "# Roaming\n\n" + " ".join(f"p{i}" for i in range(12))
    chunks = hierarchical_chunks(text, max_tokens=5, overlap_tokens=1, min_tokens=2)
    parent, *children = chunks
    assert parent.kind == "section"
    assert parent.heading_path == ("Roaming",)
    assert len(children) == 3
    assert all(child.kind == "chunk" and child.parent_ordinal == parent.ordinal for child in children)
    assert children[0].content.endswith("p4")
    assert children[1].content.startswith("p4")


def test_nests_markdown_heading_path():
    chunks = hierarchical_chunks("# Produto\n## Ativação\n" + "texto " * 8,
                                 max_tokens=50, overlap_tokens=0, min_tokens=2)
    assert chunks[0].heading_path == ("Produto", "Ativação")
