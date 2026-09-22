from chienami_indexer.hashing import content_hash


def test_same_text_same_hash():
    assert content_hash("hello") == content_hash("hello")


def test_different_text_different_hash():
    assert content_hash("hello") != content_hash("world")


def test_hash_is_hex_sha256_length():
    h = content_hash("some text")
    assert len(h) == 64
    int(h, 16)  # raises ValueError if not hex
