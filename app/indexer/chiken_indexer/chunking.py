"""Chunking方針の初期実装（design書5.3節はたたき台未確定のため本実装で最初の方針を定める）。

段落（空行区切り）をなるべく壊さずにまとめ、chunk_size文字を目安に分割する。
1段落がchunk_sizeを超える場合のみハード分割する。チャンク間にはoverlap文字を重ねて、
チャンク境界での文脈欠落を緩和する。Recall評価（後続Issue）の結果次第でパラメータや
分割単位を見直す前提の初期実装。
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class Chunk:
    index: int
    text: str


def chunk_text(text: str, chunk_size: int = 1000, overlap: int = 100) -> list[Chunk]:
    if chunk_size <= 0:
        raise ValueError("chunk_size must be positive")
    if overlap < 0 or overlap >= chunk_size:
        raise ValueError("overlap must be in [0, chunk_size)")

    paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
    if not paragraphs:
        return []

    # 各チャンクの「新規部分」の目標文字数。overlap分は前チャンクの末尾から引き継ぐため、
    # core_size + overlap が最終チャンク長の上限（chunk_size）になるよう、あらかじめ
    # overlap分を差し引いておく。
    core_size = chunk_size - overlap

    core_chunks: list[str] = []
    current = ""
    for para in paragraphs:
        candidate = f"{current}\n\n{para}" if current else para
        if len(candidate) <= core_size:
            current = candidate
            continue

        if current:
            core_chunks.append(current)

        if len(para) <= core_size:
            current = para
        else:
            for start in range(0, len(para), core_size):
                piece = para[start : start + core_size]
                if piece:
                    core_chunks.append(piece)
            current = ""

    if current:
        core_chunks.append(current)

    if overlap == 0 or len(core_chunks) <= 1:
        overlapped = core_chunks
    else:
        overlapped = [core_chunks[0]]
        for i in range(1, len(core_chunks)):
            prev_tail = core_chunks[i - 1][-overlap:]
            overlapped.append(f"{prev_tail}{core_chunks[i]}")

    return [Chunk(index=i, text=c) for i, c in enumerate(overlapped)]
