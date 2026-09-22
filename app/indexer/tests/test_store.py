from chienami_indexer.store import point_id


def test_point_id_is_deterministic():
    assert point_id("doc-1", 0) == point_id("doc-1", 0)


def test_point_id_differs_by_chunk_index():
    assert point_id("doc-1", 0) != point_id("doc-1", 1)


def test_point_id_differs_by_document():
    assert point_id("doc-1", 0) != point_id("doc-2", 0)


def test_point_id_is_valid_uuid_string():
    import uuid

    pid = point_id("doc-1", 0)
    uuid.UUID(pid)  # raises ValueError if not a valid UUID
