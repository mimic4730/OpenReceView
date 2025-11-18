# src/openreceview/models/uke_receipt.py
from __future__ import annotations
from dataclasses import dataclass, field
from typing import List, Optional

from openreceview.models.uke_record import UkeRecord
from openreceview.models.receipt_header import ReceiptHeader


@dataclass
class UkeReceipt:
    """
    1レセプト（RE〜次のRE直前まで）のまとまり。
    """
    index: int                   # レセプト通し番号（1始まり）
    start_line: int              # 最初のレコード行番号（通常 RE）
    records: List[UkeRecord] = field(default_factory=list)
    header: Optional[ReceiptHeader] = None  # ヘッダ情報
    diseases: List[DiseaseEntry] = field(default_factory=list)
    
    @property
    def end_line(self) -> int:
        """このレセプトの最後のレコード行番号"""
        if not self.records:
            return self.start_line
        return self.records[-1].line_no

@dataclass
class DiseaseEntry:
    code: str
    start_date: str
    outcome: str
    is_main: bool
    modifier_codes: list[str] = field(default_factory=list)