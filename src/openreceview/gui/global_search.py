# src/openreceview/gui/global_search.py

from __future__ import annotations

import csv

from dataclasses import dataclass
from typing import Callable, Dict, Iterable, List, Optional, Tuple

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
    QCheckBox,
    QFileDialog,
    QMessageBox,
    QRadioButton,
    QButtonGroup,
)

from openreceview.models.uke_receipt import UkeReceipt


@dataclass
class GlobalSearchResult:
    receipt_index: int   # MainWindow._receipts の添字
    patient_id: str
    receipt_no: str
    name: str
    match_label: str     # 「一致項目」列に表示するテキスト


class GlobalSearchDialog(QDialog):
    """
    レセ電ビューワー風の総合検索ダイアログ。
    """

    _SEARCH_FIELDS: List[Tuple[str, str]] = [
        ("name",           "名前"),
        ("patient_id",     "患者番号"),
        ("receipt_no",     "レセプト番号（仮）"),
        ("disease",        "傷病名"),
        ("drug",           "医薬品"),
        ("proc",           "診療行為"),
        ("points",         "点数"),
        ("year_month",     "診療年月"),
        ("insurer",        "保険者"),
        ("futansha_number","負担者番号"),
        ("department",     "診療科"),
        ("public_expense", "公費"),
        ("special_note",   "特記事項"),
        ("free_comment",   "フリーコメント内容"),
    ]

    def __init__(
        self,
        parent: Optional[QWidget],
        receipts: Iterable[UkeReceipt],
        on_jump_to_receipt: Callable[[int], None],
        # ここからは任意の名称解決ヘルパ
        get_disease_name: Callable[[str], str] | None = None,
        get_modifier_name: Callable[[str], str] | None = None,
        get_shinryo_name: Callable[[str], str] | None = None,
        get_drug_name: Callable[[str], str] | None = None,
        get_material_name: Callable[[str], str] | None = None,
        get_comment_text: Callable[[str], str] | None = None,
    ) -> None:
        super().__init__(parent)
        # 呼び出し側から渡されたヘルパを保存（なければダミー関数）
        self.get_disease_name = get_disease_name or (lambda code: "")
        self.get_modifier_name = get_modifier_name or (lambda code: "")
        self.get_shinryo_name = get_shinryo_name or (lambda code: "")
        self.get_drug_name = get_drug_name or (lambda code: "")
        self.get_material_name = get_material_name or (lambda code: "")
        self.get_comment_text = get_comment_text or (lambda code: "")

        # receipts は list 化して index を使えるようにしておく
        self._receipts: List[UkeReceipt] = list(receipts)
        self._on_jump_to_receipt = on_jump_to_receipt
        self._field_checkboxes: Dict[str, QCheckBox] = {}
        self._results: List[GlobalSearchResult] = []

        self._init_widgets()
        self._init_layout()
        self._connect_signals()

        for key in ("name", "patient_id", "disease"):
            if key in self._field_checkboxes:
                self._field_checkboxes[key].setChecked(True)

    # ─ UI 構築 ─────────────────────────────────────────────
    def _init_widgets(self) -> None:
        self.keyword_edit = QLineEdit(self)
        self.keyword_edit.setPlaceholderText("検索語を入力（例: 山田, 7153018, ガスター など）")

        # 左ペイン：検索対象
        self.left_group = QGroupBox("検索対象", self)
        left_layout = QVBoxLayout(self.left_group)

        for key, label in self._SEARCH_FIELDS:
            cb = QCheckBox(label, self.left_group)
            self._field_checkboxes[key] = cb
            left_layout.addWidget(cb)

        # 検索モード（OR / AND）
        self.mode_group = QGroupBox("検索モード", self.left_group)
        mode_layout = QHBoxLayout(self.mode_group)
        self.rb_mode_or = QRadioButton("OR（いずれか一致）", self.mode_group)
        self.rb_mode_and = QRadioButton("AND（すべて一致）", self.mode_group)
        self.rb_mode_or.setChecked(True)
        mode_layout.addWidget(self.rb_mode_or)
        mode_layout.addWidget(self.rb_mode_and)
        mode_layout.addStretch(1)
        left_layout.addWidget(self.mode_group)

        left_layout.addStretch(1)

        # 右ペイン：検索結果
        self.result_table = QTableWidget(self)
        self.result_table.setColumnCount(4)
        self.result_table.setHorizontalHeaderLabels(
            ["患者番号", "レセプト番号", "名前", "一致項目"]
        )
        self.result_table.verticalHeader().setVisible(False)
        self.result_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.result_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.result_table.setSelectionMode(QTableWidget.SingleSelection)
        self.result_table.horizontalHeader().setStretchLastSection(True)

        # 列ヘッダのクリックでソートを有効化
        self.result_table.setSortingEnabled(True)

        self.result_group = QGroupBox("検索結果", self)
        result_layout = QVBoxLayout(self.result_group)
        result_layout.addWidget(self.result_table)

        # スプリッタ
        self.splitter = QSplitter(Qt.Horizontal, self)
        self.splitter.addWidget(self.left_group)
        self.splitter.addWidget(self.result_group)
        self.splitter.setStretchFactor(0, 0)
        self.splitter.setStretchFactor(1, 1)

        # ボタン
        self.button_box = QDialogButtonBox(self)
        self.btn_search = QPushButton("検索", self)
        self.btn_export = QPushButton("CSV出力", self)
        self.btn_close = QPushButton("閉じる", self)

        self.button_box.addButton(self.btn_search, QDialogButtonBox.AcceptRole)
        self.button_box.addButton(self.btn_export, QDialogButtonBox.ActionRole)
        self.button_box.addButton(self.btn_close, QDialogButtonBox.RejectRole)

    def _init_layout(self) -> None:
        root = QVBoxLayout(self)

        top_row = QHBoxLayout()
        top_row.addWidget(QLabel("検索語:", self))
        top_row.addWidget(self.keyword_edit)
        root.addLayout(top_row)

        root.addWidget(self.splitter)
        root.addWidget(self.button_box)

        self.setLayout(root)
        self.resize(900, 500)

    def _connect_signals(self) -> None:
        self.btn_close.clicked.connect(self.reject)
        self.btn_search.clicked.connect(self._on_search_clicked)
        self.keyword_edit.returnPressed.connect(self._on_search_clicked)
        self.result_table.itemDoubleClicked.connect(self._on_result_activated)
        self.btn_export.clicked.connect(self._on_export_csv)
        # 検索モード（OR / AND）切り替え時にも即座に再検索
        self.rb_mode_or.toggled.connect(self._on_mode_changed)
        self.rb_mode_and.toggled.connect(self._on_mode_changed)

    def _is_and_mode(self) -> bool:
        """
        現在の検索モードが AND かどうかを返す。
        """
        # AND ラジオボタンがチェックされているときのみ AND モード
        return getattr(self, "rb_mode_and", None) is not None and self.rb_mode_and.isChecked()

    # ─ 検索ロジック ─────────────────────────────────────────
    def _on_search_clicked(self) -> None:
        keyword = self.keyword_edit.text().strip()
        if not keyword:
            return

        active_keys = [
            key for key, cb in self._field_checkboxes.items() if cb.isChecked()
        ]
        if not active_keys:
            return

        and_mode = self._is_and_mode()

        lowered = keyword.lower()

        # いったんソートを無効にしてからテーブルをクリア・再構築する
        was_sorting_enabled = self.result_table.isSortingEnabled()
        self.result_table.setSortingEnabled(False)

        self._results.clear()
        self.result_table.setRowCount(0)

        for idx, receipt in enumerate(self._receipts):
            for res in self._match_receipt(idx, receipt, lowered, active_keys, and_mode):
                row = self.result_table.rowCount()
                self.result_table.insertRow(row)

                # 0列目（患者番号）に、この行が対応するレセプトのインデックスを保持しておく
                item_patient = QTableWidgetItem(res.patient_id)
                item_patient.setData(Qt.UserRole, res.receipt_index)
                self.result_table.setItem(row, 0, item_patient)

                self.result_table.setItem(row, 1, QTableWidgetItem(res.receipt_no))
                self.result_table.setItem(row, 2, QTableWidgetItem(res.name))
                self.result_table.setItem(row, 3, QTableWidgetItem(res.match_label))

                self._results.append(res)

        # 検索結果の表示後にソート設定を元に戻す
        self.result_table.setSortingEnabled(was_sorting_enabled)

    def _match_receipt(
        self,
        index: int,
        receipt: UkeReceipt,
        lowered_keyword: str,
        active_keys: List[str],
        and_mode: bool,
    ) -> List[GlobalSearchResult]:
        header = receipt.header
        if header is None:
            return []

        patient_id = (getattr(header, "patient_id", "") or "").strip()
        name = (getattr(header, "name", "") or "").strip()
        receipt_no = (
            (getattr(header, "receipt_no", "") or "").strip()
            or str(index + 1)  # 仮の連番
        )

        # AND / OR 双方に対応するため、いったん「どの検索項目でヒットしたか」を集計する
        # key -> bool（ヒットしたかどうか）
        matched_by_key: Dict[str, bool] = {}
        # 実際の「一致項目」表示用ラベルのリスト
        match_labels: List[Tuple[str, str]] = []  # (key, label)

        def record_match(key: str, label: str) -> None:
            matched_by_key[key] = True
            match_labels.append((key, label))

        # 1) ヘッダ系
        if "name" in active_keys:
            if lowered_keyword in name.lower():
                record_match("name", "名前")

        if "patient_id" in active_keys:
            if lowered_keyword in patient_id.lower():
                record_match("patient_id", "患者番号")

        if "receipt_no" in active_keys:
            if lowered_keyword in receipt_no.lower():
                record_match("receipt_no", "レセプト番号")

        if "year_month" in active_keys:
            ym = (getattr(header, "year_month", "") or "").strip()
            if lowered_keyword in ym.lower():
                record_match("year_month", f"診療年月: {ym}")

        if "insurer" in active_keys:
            insurer = (getattr(header, "insurer_number", "") or "").strip()
            if lowered_keyword in insurer.lower():
                record_match("insurer", f"保険者: {insurer}")

        if "department" in active_keys:
            dept = (getattr(header, "department", "") or "").strip()
            if dept and lowered_keyword in dept.lower():
                record_match("department", f"診療科: {dept}")

        # 2) レコード系
        # 2) レコード系
        for rec in receipt.records:
            rec_type = rec.record_type
            raw_lower = rec.raw.lower()
            f = getattr(rec, "fields", []) or []

            # -------------------------
            # 傷病名 (SYレコード)
            # -------------------------
            if "disease" in active_keys and rec_type == "SY":
                # SY:
                # 1: 傷病名コード
                # 5: 傷病名称（レコード内）
                code = f[1].strip() if len(f) > 1 and f[1] else ""
                name_from_master = self.get_disease_name(code) or ""
                name_in_sy = f[5].strip() if len(f) > 5 and f[5] else ""

                # コード / マスタ名称 / レコード内名称 / raw の全部を検索対象にする
                text = " ".join(
                    part
                    for part in [code, name_from_master, name_in_sy, rec.raw]
                    if part
                ).lower()

                if lowered_keyword in text:
                    record_match("disease", f"傷病名 (行 {rec.line_no})")

            # -------------------------
            # 診療行為 (SI)
            # -------------------------
            if "proc" in active_keys and rec_type == "SI":
                # SI:
                # 1: 診療識別
                # 2: 負担区分
                # 3: 診療行為コード
                code = f[3].strip() if len(f) > 3 and f[3] else ""
                name_from_master = self.get_shinryo_name(code) or ""

                text = " ".join(
                    part
                    for part in [code, name_from_master, rec.raw]
                    if part
                ).lower()

                if lowered_keyword in text:
                    record_match("proc", f"診療行為 (行 {rec.line_no})")

            # -------------------------
            # 医薬品 (IY)
            # -------------------------
            if "drug" in active_keys and rec_type == "IY":
                # IY も SI 同様に 3 列目をコードと仮定
                code = f[3].strip() if len(f) > 3 and f[3] else ""
                name_from_master = self.get_drug_name(code) or ""

                text = " ".join(
                    part
                    for part in [code, name_from_master, rec.raw]
                    if part
                ).lower()

                if lowered_keyword in text:
                    record_match("drug", f"医薬品 (行 {rec.line_no})")

            # -------------------------
            # 点数（とりあえず SI / IY / TO の raw に対して部分一致）
            # -------------------------
            if "points" in active_keys and rec_type in ("SI", "IY", "TO"):
                if lowered_keyword in raw_lower:
                    record_match("points", f"点数関連 (行 {rec.line_no})")

            # -------------------------
            # 公費・負担者番号（KO, SN など公費関連をざっくり）
            # -------------------------
            if "public_expense" in active_keys and rec_type in ("KO", "SN"):
                if lowered_keyword in raw_lower:
                    record_match("public_expense", f"公費関連 (行 {rec.line_no})")

            if "futansha_number" in active_keys and rec_type in ("KO", "SN"):
                if lowered_keyword in raw_lower:
                    record_match("futansha_number", f"負担者番号関連 (行 {rec.line_no})")

            # -------------------------
            # 特記事項・フリーコメント (CO)
            # -------------------------
            if rec_type == "CO":
                # もしコメントコードの位置がわかっていればここで拾う（例: f[3]）
                # comment_code = f[3].strip() if len(f) > 3 and f[3] else ""
                # comment_text_from_master = self.get_comment_text(comment_code) or ""
                # text = " ".join(
                #     part for part in [comment_code, comment_text_from_master, rec.raw] if part
                # ).lower()
                text = raw_lower  # ひとまず従来どおり raw ベース

                if "special_note" in active_keys and lowered_keyword in text:
                    record_match("special_note", f"特記事項/コメント (行 {rec.line_no})")
                if "free_comment" in active_keys and lowered_keyword in text:
                    record_match("free_comment", f"フリーコメント (行 {rec.line_no})")
        # ここまでで match_labels / matched_by_key が埋まっている

        if not match_labels:
            return []

        # AND モードの場合は、「選択されたすべての検索項目でヒットしたレセプト」だけを返す
        if and_mode:
            # すべての active_keys が少なくとも1回はヒットしているか？
            for key in active_keys:
                if not matched_by_key.get(key, False):
                    return []

            # 一致項目ラベルは、重複を除いてまとめて表示
            seen = set()
            merged_labels: List[str] = []
            for key, label in match_labels:
                if label not in seen:
                    seen.add(label)
                    merged_labels.append(label)

            return [
                GlobalSearchResult(
                    receipt_index=index,
                    patient_id=patient_id,
                    receipt_no=receipt_no,
                    name=name,
                    match_label=" / ".join(merged_labels),
                )
            ]

        # OR モード（従来どおり、ヒットした項目ごとに1行ずつ返す）
        results: List[GlobalSearchResult] = []
        for _key, label in match_labels:
            results.append(
                GlobalSearchResult(
                    receipt_index=index,
                    patient_id=patient_id,
                    receipt_no=receipt_no,
                    name=name,
                    match_label=label,
                )
            )
        return results

    def _on_export_csv(self) -> None:
        """
        検索結果テーブルの内容を CSV でエクスポートする。
        テーブルの表示順（＝ソート後の順）で出力する。
        """
        row_count = self.result_table.rowCount()
        if row_count == 0:
            QMessageBox.information(self, "CSV出力", "出力可能な検索結果がありません。")
            return

        path, selected_filter = QFileDialog.getSaveFileName(
            self,
            "検索結果をCSV出力",
            "search_results.csv",
            "CSV ファイル (*.csv);;すべてのファイル (*.*)",
        )
        if not path:
            return  # キャンセル

        try:
            with open(path, "w", newline="", encoding="utf-8-sig") as fp:
                writer = csv.writer(fp)
                # ヘッダ
                writer.writerow(["患者番号", "レセプト番号", "名前", "一致項目"])

                # テーブルの表示順で書き出し
                for row in range(row_count):
                    patient_item = self.result_table.item(row, 0)
                    receipt_item = self.result_table.item(row, 1)
                    name_item = self.result_table.item(row, 2)
                    match_item = self.result_table.item(row, 3)

                    patient = patient_item.text() if patient_item is not None else ""
                    receipt_no = receipt_item.text() if receipt_item is not None else ""
                    name = name_item.text() if name_item is not None else ""
                    match_label = match_item.text() if match_item is not None else ""

                    writer.writerow([patient, receipt_no, name, match_label])

        except Exception as e:
            QMessageBox.critical(
                self,
                "CSV出力エラー",
                f"CSV出力中にエラーが発生しました:\n{e}",
            )
            return

        QMessageBox.information(self, "CSV出力", "検索結果のCSV出力が完了しました。")

    # ─ 結果クリック時 ─────────────────────────────────────
    def _on_result_activated(self, item: QTableWidgetItem) -> None:
        row = item.row()
        # 0列目のアイテムに保存している receipt_index を取得する
        id_item = self.result_table.item(row, 0)
        if id_item is None:
            return

        idx = id_item.data(Qt.UserRole)
        if idx is None:
            return

        try:
            receipt_index = int(idx)
        except (TypeError, ValueError):
            return

        self._on_jump_to_receipt(receipt_index)
        # 検索ウインドウはそのまま開いていても良い（ビューワー風の挙動）


    # ─ レセプト一覧の差し替え（MainWindow から呼び出し） ────────────────
    def update_receipts(self, receipts: Iterable[UkeReceipt]) -> None:
        """
        メインウィンドウ側でレセプト一覧が更新されたときに呼び出して、
        検索対象となるレセプト一覧を差し替える。
        """
        self._receipts = list(receipts)

        # ついでに前回の検索結果もクリアしておく
        self._results.clear()
        self.result_table.setRowCount(0) 
    def _on_mode_changed(self, checked: bool) -> None:
        """OR/AND ラジオボタンが切り替わったときに再検索する。"""
        # チェックが入った側だけで動作させる
        if not checked:
            return
        # 現在のキーワードとチェックボックス選択を使って再検索
        self._on_search_clicked()