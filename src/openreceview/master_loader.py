# src/openreceview/master_loader.py
from __future__ import annotations
from pathlib import Path
import csv
import io
from typing import Dict, Tuple, Any
import json
import os

# マスタ読み込み結果をプロセス内でキャッシュするための簡易ストア
# キー: (種類, パスのタプル, 追加パラメータ...)
_MASTER_CACHE: Dict[tuple, Any] = {}

_CACHE_DIR = Path(os.path.expanduser("~")) / ".openreceview_cache"

def _get_cache_dir() -> Path:
    _CACHE_DIR.mkdir(parents=True, exist_ok=True)
    return _CACHE_DIR

def _disk_cache_path(kind: str, signature: str) -> Path:
    return _get_cache_dir() / f"{kind}_{signature}.json"

def _build_signature(paths: list[Path]) -> str:
    sig_parts = []
    for p in sorted(paths, key=lambda x: str(x)):
        try:
            stat = p.stat()
            sig_parts.append(f"{p.name}:{stat.st_mtime_ns}:{stat.st_size}")
        except FileNotFoundError:
            sig_parts.append(f"{p.name}:missing")
    return "_".join(sig_parts)

def _load_simple_master_from_disk(kind: str, paths: list[Path]) -> dict[str, dict[str, str]] | None:
    signature = _build_signature(paths)
    cache_file = _disk_cache_path(kind, signature)
    if not cache_file.exists():
        return None
    try:
        with cache_file.open("r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict):
            return data
    except Exception:
        pass
    return None

def _save_simple_master_to_disk(kind: str, paths: list[Path], data: dict[str, dict[str, str]]) -> None:
    signature = _build_signature(paths)
    cache_file = _disk_cache_path(kind, signature)
    try:
        with cache_file.open("w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False)
    except Exception:
        pass

def _load_modifier_from_disk(paths: list[Path]) -> tuple[dict[str, str], dict[str, str]] | None:
    signature = _build_signature(paths)
    name_file = _disk_cache_path("modifier_name", signature)
    kana_file = _disk_cache_path("modifier_kana", signature)
    if not name_file.exists() or not kana_file.exists():
        return None
    try:
        with name_file.open("r", encoding="utf-8") as f:
            name_by_code = json.load(f)
        with kana_file.open("r", encoding="utf-8") as f:
            kana_by_code = json.load(f)
        if isinstance(name_by_code, dict) and isinstance(kana_by_code, dict):
            return (name_by_code, kana_by_code)
    except Exception:
        pass
    return None

def _save_modifier_to_disk(paths: list[Path], name_by_code: dict[str, str], kana_by_code: dict[str, str]) -> None:
    signature = _build_signature(paths)
    name_file = _disk_cache_path("modifier_name", signature)
    kana_file = _disk_cache_path("modifier_kana", signature)
    try:
        with name_file.open("w", encoding="utf-8") as f:
            json.dump(name_by_code, f, ensure_ascii=False)
        with kana_file.open("w", encoding="utf-8") as f:
            json.dump(kana_by_code, f, ensure_ascii=False)
    except Exception:
        pass

def clear_master_cache() -> None:
    """
    すべてのマスタキャッシュをクリアする。

    「マスタファイルを差し替えたので読み直したい」場合などに呼び出す。
    """
    _MASTER_CACHE.clear()

def _decode_text(raw: bytes) -> str:
    """複数の日本語エンコーディングを順に試してテキスト化するヘルパ.

    - Windows 系: cp932
    - 一般的な Shift-JIS: shift_jis
    - UTF-8 / UTF-8 BOM もフォールバックとして試す
    """
    for enc in ("cp932", "shift_jis", "utf-8", "utf-8-sig"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    # 最後の保険: cp932 で壊れてもよいので無理やり読む
    return raw.decode("cp932", errors="ignore")

def _detect_delimiter(text: str) -> str:
    """サンプル行から区切り文字を推定."""
    sample = "\n".join(text.splitlines()[:5])
    if "\t" in sample and ("," not in sample or sample.count("\t") >= sample.count(",")):
        return "\t"
    return ","

def load_disease_master(paths: list[Path]) -> Dict[str, Dict[str, str]]:
    """
    傷病名マスタ(b/hb)を複数ファイルから読み込み、
    code -> {"name": 漢字名, "kana": カナ} の dict を返す。
    """
    key = ("disease", tuple(sorted(str(p) for p in paths)))
    if key in _MASTER_CACHE:
        return _MASTER_CACHE[key]  # type: ignore[return-value]

    cached = _load_simple_master_from_disk("disease", paths)
    if cached is not None:
        _MASTER_CACHE[key] = cached
        return cached

    master: Dict[str, Dict[str, str]] = {}

    for path in paths:
        raw = path.read_bytes()
        text = _decode_text(raw)
        delim = _detect_delimiter(text)

        reader = csv.reader(io.StringIO(text), delimiter=delim)

        for row in reader:
            if not row:
                continue

            def safe(idx: int) -> str:
                return row[idx].strip() if len(row) > idx and row[idx] is not None else ""

            code = safe(2) or safe(3)   # 3列目→4列目
            if not code:
                continue

            name = safe(5) or safe(7)  # 6列目→8列目
            kana = safe(9)             # 10列目

            if not name and not kana:
                continue

            master[code] = {"name": name, "kana": kana}

    _save_simple_master_to_disk("disease", paths, master)
    _MASTER_CACHE[key] = master
    return master

def load_modifier_master(paths: list[Path]) -> Tuple[Dict[str, str], Dict[str, str]]:
    """
    修飾語マスタ(Z…)を複数ファイルから読み込み、
    (code -> name, code -> kana) の2つの dict を返す。
    """
    key = ("modifier", tuple(sorted(str(p) for p in paths)))
    if key in _MASTER_CACHE:
        return _MASTER_CACHE[key]  # type: ignore[return-value]

    cached = _load_modifier_from_disk(paths)
    if cached is not None:
        name_by_code, kana_by_code = cached
        _MASTER_CACHE[key] = (name_by_code, kana_by_code)
        return name_by_code, kana_by_code

    name_by_code: Dict[str, str] = {}
    kana_by_code: Dict[str, str] = {}

    for path in paths:
        raw = path.read_bytes()
        text = _decode_text(raw)
        delim = _detect_delimiter(text)

        reader = csv.reader(io.StringIO(text), delimiter=delim)

        for row in reader:
            if not row:
                continue

            def safe(idx: int) -> str:
                return row[idx].strip() if len(row) > idx and row[idx] is not None else ""

            kind = safe(1)   # 2列目
            code = safe(2)   # 3列目
            if kind and kind != "Z":
                continue
            if not code:
                continue

            name = safe(6)   # 7列目
            kana = safe(9)   # 10列目

            if name:
                name_by_code[code] = name
            if kana:
                kana_by_code[code] = kana

    _save_modifier_to_disk(paths, name_by_code, kana_by_code)
    result: Tuple[Dict[str, str], Dict[str, str]] = (name_by_code, kana_by_code)
    _MASTER_CACHE[key] = result
    return result

def load_shinryo_master(paths: list[Path]) -> Dict[str, Dict[str, str]]:
    """診療行為マスタを読み込み、code -> {name, kana} 辞書を返す。"""
    key = ("shinryo", tuple(sorted(str(p) for p in paths)))
    if key in _MASTER_CACHE:
        return _MASTER_CACHE[key]  # type: ignore[return-value]

    cached = _load_simple_master_from_disk("shinryo", paths)
    if cached is not None:
        _MASTER_CACHE[key] = cached
        return cached

    master = load_simple_master(
        paths,
        code_col=2,  # 診療行為コード
        name_col=4,  # 初診料 など（漢字）
        kana_col=6,  # ｼｮｼﾝﾘｮｳ など（カナ）
    )
    _save_simple_master_to_disk("shinryo", paths, master)
    _MASTER_CACHE[key] = master
    return master

def load_chouzai_master(paths: list[Path]) -> Dict[str, Dict[str, str]]:
    """調剤行為マスタ (M)"""
    key = ("chouzai", tuple(sorted(str(p) for p in paths)))
    if key in _MASTER_CACHE:
        return _MASTER_CACHE[key]  # type: ignore[return-value]

    cached = _load_simple_master_from_disk("chouzai", paths)
    if cached is not None:
        _MASTER_CACHE[key] = cached
        return cached

    master = load_simple_master(
        paths,
        code_col=2,  # 調剤行為コード
        name_col=4,  # 調剤基本料１ など
        kana_col=6,  # ﾁｮｳｻﾞｲｷﾎﾝﾘｮｳ など
    )
    _save_simple_master_to_disk("chouzai", paths, master)
    _MASTER_CACHE[key] = master
    return master

def load_drug_master(paths: list[Path]) -> Dict[str, Dict[str, str]]:
    """医薬品マスタ (Y)"""
    key = ("drug", tuple(sorted(str(p) for p in paths)))
    if key in _MASTER_CACHE:
        return _MASTER_CACHE[key]  # type: ignore[return-value]

    cached = _load_simple_master_from_disk("drug", paths)
    if cached is not None:
        _MASTER_CACHE[key] = cached
        return cached

    master = load_simple_master(
        paths,
        code_col=2,  # 医薬品コード
        name_col=4,  # ガスター散２％
        kana_col=6,  # ｶﾞｽﾀｰｻﾝ2%
    )
    _save_simple_master_to_disk("drug", paths, master)
    _MASTER_CACHE[key] = master
    return master

def load_material_master(paths: list[Path]) -> Dict[str, Dict[str, str]]:
    """特定器材マスタ (T)"""
    key = ("material", tuple(sorted(str(p) for p in paths)))
    if key in _MASTER_CACHE:
        return _MASTER_CACHE[key]  # type: ignore[return-value]

    cached = _load_simple_master_from_disk("material", paths)
    if cached is not None:
        _MASTER_CACHE[key] = cached
        return cached

    master = load_simple_master(
        paths,
        code_col=2,  # 器材コード
        name_col=4,  # 半切
        kana_col=6,  # ﾊﾝｾﾂ
    )
    _save_simple_master_to_disk("material", paths, master)
    _MASTER_CACHE[key] = master
    return master

def load_ward_master(paths: list[Path]) -> Dict[str, Dict[str, str]]:
    """病棟コードマスタ"""
    key = ("ward", tuple(sorted(str(p) for p in paths)))
    if key in _MASTER_CACHE:
        return _MASTER_CACHE[key]  # type: ignore[return-value]

    cached = _load_simple_master_from_disk("ward", paths)
    if cached is not None:
        _MASTER_CACHE[key] = cached
        return cached

    master = load_simple_master(
        paths,
        code_col=2,  # 病棟コード
        name_col=4,  # 高度急性期機能病棟０１
        kana_col=6,  # ｺｳﾄﾞｷｭｳｾｲｷｷﾉｳ01
    )
    _save_simple_master_to_disk("ward", paths, master)
    _MASTER_CACHE[key] = master
    return master

# （必要になったら）
def load_comment_master(paths: list[Path]) -> Dict[str, Dict[str, str]]:
    """コメントマスタ (C)"""
    key = ("comment", tuple(sorted(str(p) for p in paths)))
    if key in _MASTER_CACHE:
        return _MASTER_CACHE[key]  # type: ignore[return-value]

    cached = _load_simple_master_from_disk("comment", paths)
    if cached is not None:
        _MASTER_CACHE[key] = cached
        return cached

    master = load_simple_master(
        paths,
        code_col=3,  # コメントコード
        name_col=6,  # 別途コメントあり
        kana_col=8,  # ﾍﾞｯﾄｺﾒﾝﾄｱﾘ
    )
    _save_simple_master_to_disk("comment", paths, master)
    _MASTER_CACHE[key] = master
    return master

def load_simple_master(
    paths: list[Path],
    *,
    code_col: int,
    name_col: int,
    kana_col: int | None = None,
) -> Dict[str, Dict[str, str]]:
    """汎用マスタ読込関数.

    列インデックスを指定して、code -> {"name": 漢字名, "kana": カナ} の dict を構築する。

    Parameters
    ----------
    paths:
        読み込むマスタファイルのパス一覧。
    code_col:
        コード列のインデックス（0始まり）。
    name_col:
        名称（漢字）列のインデックス（0始まり）。
    kana_col:
        カナ列のインデックス（0始まり）。不要な場合は None。
    """
    master: Dict[str, Dict[str, str]] = {}

    for path in paths:
        raw = path.read_bytes()
        text = _decode_text(raw)
        delim = _detect_delimiter(text)

        reader = csv.reader(io.StringIO(text), delimiter=delim)

        for row in reader:
            if not row:
                continue

            def safe(idx: int) -> str:
                return row[idx].strip() if len(row) > idx and row[idx] is not None else ""

            code = safe(code_col)
            if not code:
                continue

            name = safe(name_col)
            kana = safe(kana_col) if kana_col is not None else ""

            # 名称もカナも空ならスキップ
            if not name and not kana:
                continue

            master[code] = {"name": name, "kana": kana}

    return master

_CONFIG_FILE = _get_cache_dir() / "master_paths.json"


def save_master_paths(category: str, paths: Iterable[Path]) -> None:
    """
    各マスタ読込時に、選択されたファイルパス一覧を JSON に保存する。

    保存先:
        ~/.openreceview_master_paths.json

    JSON 形式:
        {
          "disease": [".../SByomei.txt", "..."],
          "modifier": [".../ShushokugoZ.txt", "..."],
          "shinryo": [...],
          ...
        }
    """
    config_path = Path.home() / ".openreceview_master_paths.json"

    # 既存の設定があれば読み込む
    data: dict[str, list[str]]
    if config_path.exists():
        try:
            text = config_path.read_text(encoding="utf-8")
            data = json.loads(text)
            if not isinstance(data, dict):
                data = {}
        except Exception:
            # 壊れていたら作り直す
            data = {}
    else:
        data = {}

    # このカテゴリーのパスを上書き保存
    data[category] = [str(p) for p in paths]

    # 書き出し
    try:
        config_path.write_text(
            json.dumps(data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    except Exception:
        # 書き出し失敗時はとりあえず黙って無視（アプリ動作は継続）
        pass

def load_all_master_paths() -> dict[str, list[Path]]:
    """
    保存済みのマスタパス設定をすべて読み込む。

    戻り値:
        { "disease": [Path(...), ...], "shinryo": [...], ... }
    """
    if not _CONFIG_FILE.exists():
        return {}

    try:
        with _CONFIG_FILE.open("r", encoding="utf-8") as f:
            raw = json.load(f)
        result: dict[str, list[Path]] = {}
        if isinstance(raw, dict):
            for kind, path_list in raw.items():
                if not isinstance(path_list, list):
                    continue
                result[kind] = [Path(p) for p in path_list]
        return result
    except Exception:
        return {}