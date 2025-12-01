# src/openreceview/code_tables.py

from __future__ import annotations

import json
from functools import lru_cache
from importlib import resources
from typing import Dict

# dataフォルダ内のファイル名対応表
_TABLE_FILES: Dict[str, str] = {
    "futansha_type": "futansha_type.json",
    "kakunin_kubun": "kakunin_kubun.json",
    "jushin_kubun": "jushin_kubun.json",
    "madoguchi_kbn": "madoguchi_kbn.json",
    "shinryokamei": "shinryokamei_code.json",
    "receipt_type": "receipt_type_code.json",  # ★ 追加
}


@lru_cache(maxsize=None)
def load_code_table(table_name: str) -> Dict[str, str]:
    """
    別表マスタの JSON を読み込み、コード→ラベルの dict を返す。

    - table_name: "futansha_type" など
    - JSON は openreceview/data/ 以下に配置する想定
    """
    if table_name not in _TABLE_FILES:
        raise KeyError(f"Unknown table name: {table_name}")

    filename = _TABLE_FILES[table_name]

    # openreceview.data パッケージ内のファイルを読む
    with resources.files("openreceview.data").joinpath(filename).open(
        "r", encoding="utf-8"
    ) as f:
        raw = json.load(f)

    # 1) dict 形式 {"code": "label", ...}
    if isinstance(raw, dict):
        return {str(k): str(v) for k, v in raw.items()}

    # 2) list 形式 [{"code": "...", "label": "..."}, ...] にも対応可能
    if isinstance(raw, list):
        result: Dict[str, str] = {}
        for item in raw:
            code = str(item.get("code", ""))
            label = str(item.get("label", code))
            if code:
                result[code] = label
        return result

    raise ValueError(f"Unsupported JSON format in {filename}")


# 型付きのラッパー関数を用意しておくと使う側が楽
def futansha_type_map() -> Dict[str, str]:
    return load_code_table("futansha_type")


def kakunin_kubun_map() -> Dict[str, str]:
    return load_code_table("kakunin_kubun")


def jushin_kubun_map() -> Dict[str, str]:
    return load_code_table("jushin_kubun")


def madoguchi_kbn_map() -> Dict[str, str]:
    return load_code_table("madoguchi_kbn")


def shinryokamei_map() -> Dict[str, str]:
    return load_code_table("shinryokamei")


# ─────────────────────────────────────────────────────────
# レセプト種別コード（別表5）
# receipt_type_code.json は
#   { "1112": {"description": "...", "nyuin_kbn": "入院外"}, ... }
# のような dict を想定しているため、load_code_table は使わず
# 生の JSON をそのまま返す専用ヘルパを用意する。
# ─────────────────────────────────────────────────────────

@lru_cache(maxsize=None)
def receipt_type_table() -> Dict[str, dict]:
    """
    レセプト種別コード → { description, nyuin_kbn, ... } の dict を返す。

    例:
        receipt_type_table()["1112"] ->
            {"description": "医科・医保単独・本人/世帯主・入院外",
             "nyuin_kbn": "入院外"}
    """
    filename = _TABLE_FILES["receipt_type"]
    with resources.files("openreceview.data").joinpath(filename).open(
        "r", encoding="utf-8"
    ) as f:
        raw = json.load(f)

    if not isinstance(raw, dict):
        raise ValueError(f"Unsupported JSON format in {filename} (expected dict)")

    # キーは文字列化して統一
    result: Dict[str, dict] = {}
    for k, v in raw.items():
        result[str(k)] = v if isinstance(v, dict) else {"description": str(v)}
    return result


@lru_cache(maxsize=None)
def receipt_type_inout_map() -> Dict[str, str]:
    """
    レセプト種別コード → 「入院」/「入院外」などの入院区分だけを取り出したマップ。
    JSON 内の "nyuin_kbn" フィールドを参照する。
    """
    table = receipt_type_table()
    result: Dict[str, str] = {}
    for code, info in table.items():
        if not isinstance(info, dict):
            continue
        ny = info.get("nyuin_kbn")
        if ny:
            result[str(code)] = str(ny)
    return result


def receipt_type_inout(code: str) -> str:
    """
    単一コードから「入院」/「入院外」等の入院区分を取得するユーティリティ。
    対応するコードが無い場合は空文字列を返す。
    """
    if code is None:
        return ""
    return receipt_type_inout_map().get(str(code).strip(), "")
