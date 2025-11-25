# src/openreceview/gui/header_search.py

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, List, Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLineEdit,
    QWidget,
)

from openreceview.models.uke_receipt import UkeReceipt


@dataclass
class HeaderSearchCondition:
    """
    レセプトヘッダ検索の条件。

    すべて任意入力（空文字の場合はその条件は無視する）。
    """
    patient_id: str = ""      # 患者番号
    name: str = ""            # 氏名（漢字）
    kana: str = ""            # 氏名（カナ）
    year_month: str = ""      # 診療年月（YYYYMM 想定・部分一致でも OK）
    receipt_type: str = ""    # レセプト種別（コード・文字列など）

    def is_empty(self) -> bool:
        """
        すべての条件が空かどうか。
        空の場合は「条件なし」とみなせる。
        """
        return not any(
            getattr(self, field).strip()
            for field in ("patient_id", "name", "kana", "year_month", "receipt_type")
        )


def _normalize_yyyymm(input_str: str) -> str:
    """
    入力された診療年月文字列をざっくり正規化する。

    - 数字以外を削除
    - 先頭 6 桁を YYYYMM として扱う（足りなければそのまま）

    例:
        "2025-10" -> "202510"
        "2025/10" -> "202510"
        "202510"  -> "202510"
    """
    digits = "".join(ch for ch in (input_str or "") if ch.isdigit())
    if len(digits) >= 6:
        return digits[:6]
    return digits


def match_header(receipt: UkeReceipt, cond: HeaderSearchCondition) -> bool:
    """
    1 件のレセプトが HeaderSearchCondition にマッチするか判定する。

    - 各条件が空文字の場合は無視。
    - 文字列の比較は基本的に「部分一致」（in）で行う。
    - year_month は簡単な正規化を行ってから部分一致判定。
    """
    header = receipt.header
    if header is None:
        return False

    # 患者番号
    if cond.patient_id.strip():
        target = (getattr(header, "patient_id", "") or "").strip()
        if cond.patient_id.strip() not in target:
            return False

    # 氏名（漢字）
    if cond.name.strip():
        target = (getattr(header, "name", "") or "").strip()
        if cond.name.strip() not in target:
            return False

    # 氏名（カナ）
    if cond.kana.strip():
        target = (getattr(header, "kana", "") or "").strip()
        if cond.kana.strip() not in target:
            return False

    # 診療年月（YYYYMM）
    if cond.year_month.strip():
        cond_ym = _normalize_yyyymm(cond.year_month)
        target_raw = (getattr(header, "year_month", "") or "").strip()
        target_ym = _normalize_yyyymm(target_raw)
        # cond_ym が空になった場合はマッチしない扱い
        if not cond_ym or cond_ym not in target_ym:
            return False

    # レセプト種別
    if cond.receipt_type.strip():
        target = (getattr(header, "receipt_type", "") or "").strip()
        if cond.receipt_type.strip() not in target:
            return False

    return True


def search_receipts_by_header(
    receipts: Iterable[UkeReceipt],
    cond: HeaderSearchCondition,
) -> List[int]:
    """
    レセプト一覧から、ヘッダ条件にマッチするレセプトのインデックス一覧を返す。

    戻り値のインデックスは 0 始まりで、MainWindow._receipts の添字に対応させる想定。
    """
    if cond.is_empty():
        return []

    hits: List[int] = []
    for idx, receipt in enumerate(receipts):
        if match_header(receipt, cond):
            hits.append(idx)
    return hits


class HeaderSearchDialog(QDialog):
    """
    レセプトヘッダ検索用のダイアログ。

    - 患者番号
    - 氏名（漢字）
    - 氏名（カナ）
    - 診療年月（YYYYMM）
    - レセプト種別

    を入力してもらい、HeaderSearchCondition を生成する。
    """

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("レセプトヘッダ検索")

        self._init_widgets()
        self._init_layout()

    def _init_widgets(self) -> None:
        # 入力欄
        self.patient_id_edit = QLineEdit(self)
        self.name_edit = QLineEdit(self)
        self.kana_edit = QLineEdit(self)
        self.year_month_edit = QLineEdit(self)
        self.receipt_type_edit = QLineEdit(self)

        # プレースホルダ
        self.patient_id_edit.setPlaceholderText("例: 12345")
        self.name_edit.setPlaceholderText("例: 山田太郎")
        self.kana_edit.setPlaceholderText("例: ヤマダタロウ")
        self.year_month_edit.setPlaceholderText("例: 202510")
        self.receipt_type_edit.setPlaceholderText("例: 1（医科）、3（歯科） など")

        # ボタン
        self.button_box = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel,
            orientation=Qt.Horizontal,
            parent=self,
        )
        self.button_box.accepted.connect(self.accept)
        self.button_box.rejected.connect(self.reject)

    def _init_layout(self) -> None:
        layout = QFormLayout(self)
        layout.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)

        layout.addRow("患者番号:", self.patient_id_edit)
        layout.addRow("氏名（漢字）:", self.name_edit)
        layout.addRow("氏名（カナ）:", self.kana_edit)
        layout.addRow("診療年月（YYYYMM）:", self.year_month_edit)
        layout.addRow("レセプト種別:", self.receipt_type_edit)

        layout.addRow(self.button_box)

        self.setLayout(layout)

    def get_condition(self) -> HeaderSearchCondition:
        """
        入力内容から HeaderSearchCondition を生成して返す。
        """
        return HeaderSearchCondition(
            patient_id=self.patient_id_edit.text(),
            name=self.name_edit.text(),
            kana=self.kana_edit.text(),
            year_month=self.year_month_edit.text(),
            receipt_type=self.receipt_type_edit.text(),
        )

    @staticmethod
    def get_condition_from_user(
        parent: Optional[QWidget] = None,
    ) -> Optional[HeaderSearchCondition]:
        """
        単発で呼び出すユーティリティ。

        使い方イメージ:
            cond = HeaderSearchDialog.get_condition_from_user(self)
            if cond is None:
                return  # キャンセル or 条件空

        """
        dlg = HeaderSearchDialog(parent)
        result = dlg.exec()
        if result != QDialog.Accepted:
            return None

        cond = dlg.get_condition()
        if cond.is_empty():
            # すべて空なら「条件なし」とみなして None を返す
            return None
        return cond