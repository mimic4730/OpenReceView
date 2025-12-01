# src/openreceview/models/receipt_header.py

from __future__ import annotations
from dataclasses import dataclass
from typing import Optional, Dict


@dataclass
class ReceiptHeader:
    """
    レセプト1件分のヘッダ情報（REレコードから抽出したもの）。
    """
    raw_record: str

    patient_id: Optional[str]
    year_month: Optional[str]
    receipt_type: Optional[str]

    # ★ 追加項目
    name: Optional[str] = None         # 漢字氏名
    name_kana: Optional[str] = None    # カナ氏名
    sex: Optional[str] = None          # 性別コード (1/2 など)
    birthday: Optional[str] = None     # 生年月日 (YYYYMMDD)

    field_map: Optional[Dict[str, str]] = None
    department_codes: list[str] | None = None  # 診療科名コード　["01","05",...] のように最大3件