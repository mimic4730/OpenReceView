# 例: src/openreceview/logic/receipt_type_classifier.py

from __future__ import annotations

def describe_medical_receipt_type(code: str) -> str:
    """
    医科のレセプト種別コード（別表５）から、
    「医科単独 本人 入院外」などの内訳用ラベルを生成する。

    対象:
      - 4桁数字、先頭2桁が '11' のコード（医科）
    それ以外は、コード値そのものを返す簡易表示にフォールバック。
    """
    if not code or len(code) != 4 or not code.isdigit():
        return f"種別コード {code or '-'}"

    if not code.startswith("11"):
        # 今は医科のみ対応。それ以外はそのまま返す
        return f"種別コード {code}"

    # 3桁目: 公費併用パターン
    third = code[2]
    main_map = {
        "1": "医科単独",              # 医保単独
        "2": "医科＋１種公費",        # 医保と１種の公費併用
        "3": "医科＋２種公費",        # 医保と２種の公費併用
        "4": "医科＋３種公費",        # 医保と３種の公費併用
        "5": "医科＋４種公費",        # 医保と４種の公費併用
    }
    main_label = main_map.get(third, "医科（その他）")

    # 4桁目: 本人区分＆入院/入院外
    last_digit = int(code[-1])
    # 0 は 10 扱いにしてペアを作る（9/0 が高齢7割）
    pair_value = last_digit if last_digit != 0 else 10
    group = (pair_value + 1) // 2  # 1〜5

    insured_map = {
        1: "本人",                    # 本人/世帯主
        2: "未就学者",
        3: "家族",
        4: "高齢（一般・低所得）",
        5: "高齢７割",
    }
    insured_label = insured_map.get(group, "区分不明")

    inout_label = "入院" if last_digit % 2 == 1 else "入院外"

    # 内訳行に出したい形にまとめる
    return f"{main_label} {insured_label} {inout_label}"
