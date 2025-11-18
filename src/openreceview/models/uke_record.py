# src/openreceview/models/uke_record.py

from __future__ import annotations
from dataclasses import dataclass
from typing import List


@dataclass
class UkeRecord:
    """
    UKE/レセ電ファイルの1行分を表すモデル。

    - line_no: 元ファイル上の行番号（1始まり）
    - raw: 1行丸ごとの生テキスト
    - record_type: レコード種別（先頭2文字を想定。例: RE, HO, CO, SI, IY…）
    - fields: カンマ区切りしたフィールドのリスト
    """
    line_no: int
    raw: str
    record_type: str
    fields: List[str]
