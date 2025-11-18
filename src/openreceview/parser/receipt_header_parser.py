# src/openreceview/parser/receipt_header_parser.py

from __future__ import annotations
from typing import List, Optional
import re
from openreceview.models.uke_record import UkeRecord
from openreceview.models.receipt_header import ReceiptHeader

KANA_PATTERN = re.compile(r"[ァ-ヶｦ-ﾟ]+")
KANJI_PATTERN = re.compile(r"[一-龥々]")

def _detect_yyyymm(fields: list[str]) -> Optional[str]:
    """
    フィールド列の中から診療年月っぽい値(YYYYMM)を探して返す。

    条件:
      - 6桁の数字
      - 2000 <= 年 <= 2099
      - 1 <= 月 <= 12
    """
    for f in fields:
        s = f.strip()
        if len(s) != 6 or not s.isdigit():
            continue
        year = int(s[:4])
        month = int(s[4:6])
        if 2000 <= year <= 2099 and 1 <= month <= 12:
            return s
    return None

def _detect_patient_id(fields: list[str], exclude: Optional[str] = None) -> Optional[str]:
    """
    フィールド列の中から患者番号っぽい値を探す。

    条件:
      - 2〜10桁くらいの数字
      - exclude(診療年月など) と同じ値は除外
    後方フィールドから探す（患者番号は後ろにあることが多いため）。
    """
    for f in reversed(fields):
        s = f.strip()
        if not s.isdigit():
            continue
        if exclude is not None and s == exclude:
            continue
        if 2 <= len(s) <= 10:
            return s
    return None

def _detect_name(fields: list[str]) -> Optional[str]:
    """
    漢字氏名っぽいフィールドを探す。
    - 漢字を含む
    - 長さ2文字以上
    """
    for f in fields:
        s = f.strip()
        if len(s) < 2:
            continue
        if KANJI_PATTERN.search(s):
            return s
    return None

def _detect_name_kana(fields: list[str]) -> Optional[str]:
    """
    カナ氏名っぽいフィールドを探す。
    - カタカナ（全角/半角）を含む
    - 長さ2文字以上
    - 後ろ側のフィールドを優先（今回の例だと末尾付近）
    """
    for f in reversed(fields):
        s = f.strip()
        if len(s) < 2:
            continue
        if KANA_PATTERN.search(s):
            return s
    return None

def _detect_birthday(fields: list[str]) -> Optional[str]:
    """
    生年月日 YYYYMMDD を探す。
    - 8桁の数字
    - 1900〜2099 年
    - 月1〜12, 日1〜31 (ざっくり)
    """
    for f in fields:
        s = f.strip()
        if len(s) != 8 or not s.isdigit():
            continue
        year = int(s[:4])
        month = int(s[4:6])
        day = int(s[6:8])
        if 1900 <= year <= 2099 and 1 <= month <= 12 and 1 <= day <= 31:
            return s
    return None

def _detect_sex(fields: list[str]) -> Optional[str]:
    """
    性別コードっぽい値を探す。
    - 1桁の数字
    - 1 or 2 あたりを優先
    - 氏名・診療年月・患者番号などとは重複しない位置を意識
    今回は簡単に:
      - 名前フィールドのすぐ次にある「1 or 2」を優先
    """
    name = _detect_name(fields)
    if name is None:
        # 名前位置が取れない場合は全フィールドからざっくり探す
        for f in fields:
            s = f.strip()
            if s in ("1", "2"):
                return s
        return None

    # 名前の直後あたりを優先
    try:
        idx = fields.index(name)
    except ValueError:
        idx = -1

    candidates: list[str] = []
    for i in range(idx + 1, min(len(fields), idx + 4)):
        s = fields[i].strip()
        if s in ("1", "2"):
            candidates.append(s)

    if candidates:
        return candidates[0]

    # それでも無ければ全フィールドからフォールバック
    for f in fields:
        s = f.strip()
        if s in ("1", "2"):
            return s

    return None

def parse_receipt_header(records: List[UkeRecord]) -> ReceiptHeader:
    """
    レセプト内の RE レコードからヘッダ情報を抽出する。
    """
    re_rec = next((r for r in records if r.record_type == "RE"), None)
    if re_rec is None:
        return ReceiptHeader(
            raw_record="",
            patient_id=None,
            year_month=None,
            receipt_type=None,
            name=None,
            name_kana=None,
            sex=None,
            birthday=None,
            field_map={},
        )

    fields = [f.strip() for f in re_rec.fields]

    receipt_type = fields[1] if len(fields) > 1 else None
    year_month = _detect_yyyymm(fields)
    patient_id = _detect_patient_id(fields, exclude=year_month)
    name = _detect_name(fields)
    name_kana = _detect_name_kana(fields)
    birthday = _detect_birthday(fields)
    sex = _detect_sex(fields)

    return ReceiptHeader(
        raw_record=re_rec.raw,
        patient_id=patient_id,
        year_month=year_month,
        receipt_type=receipt_type,
        name=name,
        name_kana=name_kana,
        sex=sex,
        birthday=birthday,
        field_map={
            "receipt_type_field": receipt_type or "",
            "year_month_detected": year_month or "",
            "patient_id_detected": patient_id or "",
            "name_detected": name or "",
            "name_kana_detected": name_kana or "",
            "birthday_detected": birthday or "",
            "sex_detected": sex or "",
        },
    )
