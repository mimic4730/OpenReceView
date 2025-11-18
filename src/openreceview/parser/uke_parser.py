# src/openreceview/parser/uke_parser.py
from __future__ import annotations

import re
from typing import List

from openreceview.models.uke_record import UkeRecord
from openreceview.models.uke_receipt import UkeReceipt
from openreceview.parser.receipt_header_parser import parse_receipt_header
from openreceview.models.uke_receipt import UkeReceipt, DiseaseEntry

RE_TYPE = re.compile(r"^\s*([A-Z0-9]{2})")

def parse_uke_text(text: str) -> List[UkeRecord]:
    """
    UKE/レセ電テキスト全体を行単位に分割し、UkeRecord のリストに変換する。
    """
    records: List[UkeRecord] = []

    for idx, line in enumerate(text.splitlines(), start=1):
        raw = line.rstrip("\r\n")
        if not raw.strip():
            continue

        m = RE_TYPE.match(raw)
        if m:
            record_type = m.group(1)
        else:
            record_type = "??"

        fields = raw.split(",")

        records.append(
            UkeRecord(
                line_no=idx,
                raw=raw,
                record_type=record_type,
                fields=fields,
            )
        )

    return records

def group_records_into_receipts(records: List[UkeRecord]) -> List[UkeReceipt]:
    """
    UkeRecord のシーケンスを「レセプト単位」にまとめる。
    RE が出現するたびに新しい UkeReceipt を開始し、直前までを1件とみなす。
    """
    receipts: List[UkeReceipt] = []
    current: UkeReceipt | None = None

    for rec in records:
        if rec.record_type == "RE":
            # 新しいレセプトの開始
            if current is not None:
                # ここでヘッダを解析してセットする
                current.header = parse_receipt_header(current.records)
                receipts.append(current)

            current = UkeReceipt(
                index=len(receipts) + 1,
                start_line=rec.line_no,
                records=[rec],
            )
        else:
            # 最初の RE より前の行は無視
            if current is None:
                continue
            current.records.append(rec)

    # 最後のレセプトを追加
    if current is not None:
        current.header = parse_receipt_header(current.records)  # ← 忘れがちポイントその2
        receipts.append(current)

    return receipts

def attach_diseases_to_receipt(
    receipt: UkeReceipt,
    modifier_codes_known: set[str],  # 修飾語マスタのキー集合を渡す
) -> None:
    diseases: list[DiseaseEntry] = []

    for rec in receipt.records:
        if rec.record_type != "SY":
            continue

        f = rec.fields

        def get(i: int) -> str:
            return f[i] if len(f) > i and f[i] is not None else ""

        # SY:
        # 1:レコード識別情報(SY)
        # 2:傷病名コード
        # 3:診療開始日
        # 4:転帰区分
        # 5:修飾語コード
        # 6:傷病名称
        # 7:主傷病
        # 8:補足コメント
        code          = get(1).strip()
        start         = get(2).strip()
        outcome       = get(3).strip()
        modifier_raw  = get(4).strip()   # ★ 5列目（連結修飾語）
        main_flag_raw = get(6).strip()   # 7列目 主傷病

        is_main = (main_flag_raw == "1" or main_flag_raw == "主")

        # ---- 修飾語コードを4桁ごとに分割 ----
        modifier_codes = _split_modifier_codes(modifier_raw, modifier_codes_known)

        # もし将来、「5列目以外にも単独で修飾語コードが来る」仕様が出てきたら、
        # ここで f[5:] を4桁コードスキャンして追加する、という拡張も可能。
        # for val in f[5:]:
        #     v = (val or "").strip()
        #     if len(v) == 4 and v.isdigit() and v in modifier_codes_known and v not in modifier_codes:
        #         modifier_codes.append(v)

        diseases.append(
            DiseaseEntry(
                code=code,
                start_date=start,
                outcome=outcome,
                is_main=is_main,
                modifier_codes=modifier_codes,
            )
        )

    # UkeReceipt に diseases フィールドがある想定
    receipt.diseases = diseases

def _split_modifier_codes(raw: str, known: set[str], width: int = 4) -> list[str]:
    """
    連結された修飾語コード文字列を width 桁ずつに分割し、
    マスタに存在するコードだけ返す。

    例:
        raw="20572058"  -> ["2057", "2058"]  （known に含まれていれば）
    """
    if not raw:
        return []

    digits = "".join(ch for ch in raw if ch.isdigit())
    if not digits:
        return []

    result: list[str] = []
    for i in range(0, len(digits), width):
        chunk = digits[i : i + width]
        if len(chunk) == width and chunk in known:
            result.append(chunk)
    return result

