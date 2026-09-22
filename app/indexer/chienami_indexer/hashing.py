"""差分更新判定用のcontent_hash計算（design書5.1節）。"""

import hashlib


def content_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()
