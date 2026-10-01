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


# --- 全文インデックス（Phase 4 Hybrid検索） ---

from types import SimpleNamespace  # noqa: E402

from chienami_indexer.store import QdrantStore  # noqa: E402


class _FakeQdrant:
    def __init__(self, collections=(), payload_schema=None):
        self.collections = list(collections)
        self.payload_schema = payload_schema or {}
        self.created_collections = []
        self.created_indexes = []

    def get_collections(self):
        return SimpleNamespace(collections=[SimpleNamespace(name=n) for n in self.collections])

    def create_collection(self, collection_name, vectors_config):
        self.created_collections.append(collection_name)
        self.collections.append(collection_name)

    def get_collection(self, collection_name):
        return SimpleNamespace(payload_schema=self.payload_schema)

    def create_payload_index(self, collection_name, field_name, field_schema):
        self.created_indexes.append((field_name, field_schema))


def _store(fake: _FakeQdrant) -> QdrantStore:
    store = QdrantStore.__new__(QdrantStore)
    store._client = fake
    store._collection = "col"
    store._vector_size = 4
    return store


def test_ensure_collection_creates_collection_and_text_index():
    fake = _FakeQdrant()
    _store(fake).ensure_collection()
    assert fake.created_collections == ["col"]
    [(field, schema)] = fake.created_indexes
    assert field == "text"
    assert schema.tokenizer == "multilingual"


def test_ensure_collection_adds_text_index_to_existing_collection():
    fake = _FakeQdrant(collections=["col"])
    _store(fake).ensure_collection()
    assert fake.created_collections == []
    assert [field for field, _ in fake.created_indexes] == ["text"]


def test_ensure_collection_skips_existing_text_index():
    fake = _FakeQdrant(collections=["col"], payload_schema={"text": object()})
    _store(fake).ensure_collection()
    assert fake.created_indexes == []
