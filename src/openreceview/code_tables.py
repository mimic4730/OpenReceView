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
