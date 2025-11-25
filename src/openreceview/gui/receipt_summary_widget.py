# src/openreceview/gui/receipt_summary_widget.py

from __future__ import annotations
from datetime import date
from typing import Callable, Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QWidget,
    QLabel,
    QGridLayout,
    QVBoxLayout,
    QHBoxLayout,
    QPlainTextEdit,
    QFrame,
    QCheckBox,
    QTableWidget,
    QTableWidgetItem,
    QHeaderView,
    QComboBox,
    QGroupBox,
    QSplitter,
    QTabWidget,
    QLineEdit,
)
from PySide6.QtGui import QFont
from typing import Optional
from openreceview.models.uke_receipt import UkeReceipt

from openreceview.code_tables import (
    futansha_type_map,
    kakunin_kubun_map,
    jushin_kubun_map,
    madoguchi_kbn_map,
)

class ReceiptSummaryWidget(QWidget):
    """
    レセプト1件分の概要を、レセ電ビューワー風の表レイアウトで表示するウィジェット。

    上: ヘッダ情報（診療年月・患者番号・氏名など）
    中: 傷病名一覧（主病名 / 傷病名 / 診療開始日 / 転帰）
    下: 生レコード一覧（テキスト）
    """

    def __init__(
        self,
        parent: Optional[QWidget] = None,
        get_disease_name: Optional[Callable[[str], str]] = None,
        get_disease_kana: Optional[Callable[[str], str]] = None,
        get_modifier_name: Optional[Callable[[str], str]] = None,
        get_modifier_kana: Optional[Callable[[str], str]] = None,
        get_shinryo_name: Optional[Callable[[str], str]] = None,
        get_comment_text: Optional[Callable[[str], str]] = None,
    ) -> None:
        super().__init__(parent)

        self._get_disease_name = get_disease_name
        self._get_disease_kana = get_disease_kana
        self._get_modifier_name = get_modifier_name
        self._get_modifier_kana = get_modifier_kana
        self._get_shinryo_name = get_shinryo_name
        self._get_comment_text = get_comment_text

        # カレントレセプト
        self._current_receipt: Optional[UkeReceipt] = None

        # 表示フラグ類（public属性として統一）
        self.show_disease_kana: bool = False     # 「カナを表示」
        self.show_disease_date: bool = True      # 「診療開始日を表示」
        self.date_format_mode: str = "seireki"   # "seireki" or "wareki"

        self._build_ui()

    # ─────────────────────────────
    # UI 構築
    # ─────────────────────────────
    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(4, 4, 4, 4)
        root.setSpacing(4)

        # ── 子タブ全体（患者情報 / 資格確認等 / …） ─────────────────
        self.tab_widget = QTabWidget(self)
        root.addWidget(self.tab_widget)

        # =========================================================
        # ① 患者情報タブ
        # =========================================================
        patient_page = QWidget(self)
        patient_layout = QVBoxLayout(patient_page)
        patient_layout.setContentsMargins(0, 0, 0, 0)
        patient_layout.setSpacing(4)

        splitter = QSplitter(Qt.Vertical, patient_page)

        # --- 上段: レセプト基本情報 ----------------------------
        header_group = QGroupBox("レセプト基本情報", splitter)
        header_layout = QGridLayout(header_group)
        header_layout.setHorizontalSpacing(12)
        header_layout.setVerticalSpacing(4)

        def add_header_item(index: int, title: str) -> QLabel:
            row = index // 3
            col = index % 3
            base_col = col * 2

            lbl_title = QLabel(title, header_group)
            lbl_value = QLabel("", header_group)

            header_layout.addWidget(lbl_title, row, base_col)
            header_layout.addWidget(lbl_value, row, base_col + 1)
            return lbl_value

        self.lbl_year_month    = add_header_item(0, "診療年月")
        self.lbl_receipt_type  = add_header_item(1, "レセプト種別")
        self.lbl_patient_id    = add_header_item(2, "患者番号")
        self.lbl_name          = add_header_item(3, "名前")
        self.lbl_name_kana     = add_header_item(4, "カナ氏名")
        self.lbl_sex           = add_header_item(5, "性別")
        self.lbl_birthday      = add_header_item(6, "生年月日")
        self.lbl_age           = add_header_item(7, "年齢")
        self.lbl_insurer       = add_header_item(8, "保険者番号")
        self.lbl_days          = add_header_item(9,  "診療実日数")
        self.lbl_total_points  = add_header_item(10, "合計点数【イ】")
        
        # ★ 点数チェック用
        self.lbl_calc_points   = add_header_item(11, "再計算点数（SI）")
        self.lbl_points_diff   = add_header_item(12, "差分（再計算 − 合計）")        

        # ── 中段: 傷病名一覧 + 表記設定 ─────────────────
        disease_frame = QFrame(splitter)
        disease_frame.setFrameShape(QFrame.StyledPanel)
        disease_layout = QVBoxLayout(disease_frame)
        disease_layout.setContentsMargins(6, 6, 6, 6)
        disease_layout.setSpacing(4)

        title_row = QHBoxLayout()
        lbl_disease_title = QLabel("傷病名", disease_frame)
        title_row.addWidget(lbl_disease_title)

        self.chk_show_kana = QCheckBox("カナを表示", disease_frame)
        self.chk_show_kana.setChecked(self.show_disease_kana)
        self.chk_show_kana.stateChanged.connect(self._on_display_option_changed)
        title_row.addWidget(self.chk_show_kana)

        self.chk_show_date = QCheckBox("診療開始日を表示", disease_frame)
        self.chk_show_date.setChecked(self.show_disease_date)
        self.chk_show_date.stateChanged.connect(self._on_display_option_changed)
        title_row.addWidget(self.chk_show_date)

        self.cmb_date_format = QComboBox(disease_frame)
        self.cmb_date_format.addItems(["西暦", "和暦"])
        self.cmb_date_format.setCurrentIndex(
            0 if self.date_format_mode == "seireki" else 1
        )
        self.cmb_date_format.currentIndexChanged.connect(
            self._on_date_format_changed
        )
        title_row.addWidget(self.cmb_date_format)
        title_row.addStretch(1)
        disease_layout.addLayout(title_row)

        self.disease_table = QTableWidget(disease_frame)
        self.disease_table.setColumnCount(4)
        self.disease_table.setHorizontalHeaderLabels(
            ["主病名", "傷病名", "診療開始日", "転帰"]
        )
        self.disease_table.verticalHeader().setVisible(False)
        self.disease_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.disease_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.disease_table.setSelectionMode(QTableWidget.SingleSelection)

        header = self.disease_table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.Stretch)
        header.setSectionResizeMode(2, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.ResizeToContents)

        disease_layout.addWidget(self.disease_table)

        # ── 下段: 生レコード表示 ─────────────────────
        self.raw_view = QPlainTextEdit(splitter)
        self.raw_view.setReadOnly(True)
        self.raw_view.setLineWrapMode(QPlainTextEdit.NoWrap)
        self.raw_view.setPlaceholderText("このレセプトに含まれるレコードが表示されます")

        # splitter にウィジェットを追加
        splitter.addWidget(header_group)
        splitter.addWidget(disease_frame)
        splitter.addWidget(self.raw_view)

        splitter.setStretchFactor(0, 0)  # ヘッダはあまり伸ばさない
        splitter.setStretchFactor(1, 3)  # 傷病名テーブル
        splitter.setStretchFactor(2, 1)  # 生レコード

        patient_layout.addWidget(splitter)
        self.tab_widget.addTab(patient_page, "患者情報")

        # 資格確認等タブ 
        self.qual_widget = QualificationWidget(self)
        self.tab_widget.addTab(self.qual_widget, "資格確認等")

        # 算定日タブ: SI レコードから算定日を表示
        self.santeibi_widget = SanteibiWidget(
            self,
            get_shinryo_name=self._get_shinryo_name,
            get_comment_text=self._get_comment_text,
        )
        self.tab_widget.addTab(self.santeibi_widget, "算定日")

        # TODO:「レセ電コード[個別]」用タブは
        # 後で空の QWidget を addTab しておけば OK

        # =========================================================
        # ② 以降のタブはひとまずプレースホルダ
        # =========================================================
        def add_simple_tab(title: str, message: str) -> None:
            page = QWidget(self)
            lay = QVBoxLayout(page)
            lay.addWidget(QLabel(message, page))
            lay.addStretch(1)
            self.tab_widget.addTab(page, title)

        # レセプトプレビュータブ: 実装済みウィジェット
        self.preview_widget = ReceiptPreviewWidget(
            self,
            get_shinryo_name=self._get_shinryo_name,
            get_comment_text=self._get_comment_text,
        )
        self.tab_widget.addTab(self.preview_widget, "レセプトプレビュー")
        # プレースホルダ（レセ電コード[個別]）は従来通り
        add_simple_tab("レセ電コード[個別]", "【レセ電コード[個別]】タブ（今後実装予定）")

    # ─────────────────────────────
    # 公開API: レセプトをセット
    # ─────────────────────────────
    def set_receipt(self, receipt: Optional[UkeReceipt]) -> None:
        self._current_receipt = receipt

        if receipt is None or receipt.header is None:
            self._clear()
            return

        h = receipt.header

        self.lbl_year_month.setText(h.year_month or "-")
        self.lbl_receipt_type.setText(h.receipt_type or "-")
        self.lbl_patient_id.setText(h.patient_id or "-")
        self.lbl_name.setText(h.name or "-")
        self.lbl_name_kana.setText(h.name_kana or "-")
        self.lbl_sex.setText(h.sex or "-")
        self.lbl_birthday.setText(h.birthday or "-")
        age_text = self._calc_age(h.birthday, h.year_month)
        self.lbl_age.setText(age_text or "-")

        # HO レコード（1件目）
        ho_record = next(
            (r for r in receipt.records if r.record_type == "HO"),
            None,
        )

        insurer = "-"
        days = "-"
        total_points = "-"

        if ho_record is not None:
            f = ho_record.fields
            # HO,保険者番号,記号,番号,診療実日数,合計点数,...
            if len(f) > 1 and f[1]:
                insurer = f[1]
            if len(f) > 4 and f[4]:
                days = f[4]
            if len(f) > 5 and f[5]:
                total_points = f[5]

        self.lbl_insurer.setText(insurer)
        self.lbl_days.setText(days)
        self.lbl_total_points.setText(total_points)
        
        # 点数チェック（HO 合計点数 vs SI 再計算）
        if self._current_receipt is not None:
            self._update_points_check(self._current_receipt, total_points)        

        # 資格確認等タブ: SN レコードをセット
        if hasattr(self, "qual_widget"):
            self.qual_widget.set_from_receipt(receipt)
        
        # 算定日タブ: JD レコードをセット
        if hasattr(self, "santeibi_widget"):
            self.santeibi_widget.set_from_receipt(receipt)
        # レセプトプレビューワ
        if hasattr(self, "preview_widget"):
            self.preview_widget.set_from_receipt(receipt)

        # 下側テキスト: レコード一覧
        lines: list[str] = []
        for rec in receipt.records:
            lines.append(f"{rec.line_no:05d} [{rec.record_type}] {rec.raw}")
        self.raw_view.setPlainText("\n".join(lines))

        # 傷病名一覧
        self._populate_diseases(receipt)

    # ─────────────────────────────
    # 点数再計算（SI → 合計点）
    # ─────────────────────────────
    def _calc_points_from_si(self, receipt: UkeReceipt) -> int:
        """
        SIレコードから合計点数を概算する。

        現時点では単純に
            合計 = Σ (点数フィールド × 回数フィールド)
        として計算します。
        """
        total = 0

        for rec in receipt.records:
            if rec.record_type != "SI":
                continue

            f = rec.fields

            def to_int(val: str, default: int = 0) -> int:
                val = (val or "").strip()
                if not val:
                    return default
                try:
                    # 小数が来ることは少ないはずですが念のため
                    return int(float(val))
                except ValueError:
                    return default

            tensu_raw  = f[5] if len(f) > 5 else ""
            kaisuu_raw = f[6] if len(f) > 6 else ""

            tensu  = to_int(tensu_raw, 0)
            kaisuu = to_int(kaisuu_raw, 1)  # 回数が空 or 0 の場合は 1 回とみなす

            total += tensu * (kaisuu if kaisuu > 0 else 1)

        return total

    def _update_points_check(self, receipt: UkeReceipt, ho_total_points: str | None) -> None:
        """
        HO の合計点数と SI 再計算値をヘッダに表示し、差分があれば強調表示。
        """
        # SI から再計算
        calc_total = self._calc_points_from_si(receipt)

        # HO 側の合計点数を int に
        ho_str = (ho_total_points or "").strip()
        try:
            ho_total = int(float(ho_str)) if ho_str else 0
        except ValueError:
            ho_total = 0

        diff = calc_total - ho_total

        # 表示
        self.lbl_calc_points.setText(str(calc_total) if calc_total else "-")
        self.lbl_points_diff.setText(str(diff) if diff else "0")

        # 差分があれば赤字で強調
        if diff != 0:
            self.lbl_points_diff.setStyleSheet("color: red;")
        else:
            self.lbl_points_diff.setStyleSheet("")  # デフォルトに戻す

    # ─────────────────────────────
    # 傷病名一覧の生成
    # ─────────────────────────────
    def _populate_diseases(self, receipt: UkeReceipt) -> None:
        """
        レセプト内の SY レコードから傷病名情報を復元し、
        「主病名 / 傷病名 / 診療開始日 / 転帰」の形式でテーブル表示する。
        """
        TENKI_MAP = {
            "1": "継続",   # 治癒・死亡・中止以外（多くは継続）
            "2": "治癒",
            "3": "死亡",
            "4": "中止",
        }

        self.disease_table.setRowCount(0)

        row_idx = 0
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
            start_raw     = get(2).strip()
            tenki_raw     = get(3).strip()
            modifier_raw  = get(4).strip()   # 修飾語コード（連結）
            name_in_sy    = get(5).strip()
            main_flag     = get(6).strip()

            # 主病名マーク（〇／空）
            main_mark = "〇" if main_flag and main_flag != "0" else ""

            # 修飾語コードを4桁ごとに分割
            modifier_codes = self._split_modifier_codes(modifier_raw)

            # 「修飾語＋傷病名」を組み立て
            disease_label = self._build_disease_full_name(
                code=code,
                modifier_codes=modifier_codes,
                fallback_name=name_in_sy,   # マスタにないとき用
            )

            # 診療開始日
            if self.show_disease_date:
                start_disp = self._format_ymd_for_display(start_raw)
            else:
                start_disp = ""

            # 転帰
            tenki_disp = TENKI_MAP.get(tenki_raw, "")

            # テーブルに挿入
            self.disease_table.insertRow(row_idx)
            self.disease_table.setItem(row_idx, 0, QTableWidgetItem(main_mark))
            self.disease_table.setItem(row_idx, 1, QTableWidgetItem(disease_label))
            self.disease_table.setItem(row_idx, 2, QTableWidgetItem(start_disp))
            self.disease_table.setItem(row_idx, 3, QTableWidgetItem(tenki_disp))

            row_idx += 1

    def _build_disease_full_name(
        self,
        code: str,
        modifier_codes: list[str],
        fallback_name: str = "",
    ) -> str:
        """
        傷病名コードと修飾語コード群から「修飾語＋傷病名」を作成する。

        例:
            code = "7153018"   （変形性膝関節症）
            modifier_codes = ["2057"]  （両）
            -> 「両変形性膝関節症」

        fallback_name:
            - 傷病名マスタにコードが見つからなかった場合に使う名称
              （SY 6 列目の傷病名称など）
        """
        code = (code or "").strip()

        # ベースの傷病名（マスタ優先）
        base_name = ""
        if code and self._get_disease_name is not None:
            base_name = self._get_disease_name(code) or ""

        if not base_name:
            base_name = fallback_name or code

        prefixes: list[str] = []
        suffixes: list[str] = []

        if self._get_modifier_name is not None:
            for m_code in modifier_codes:
                m_code = m_code.strip()
                if not m_code:
                    continue

                text = self._get_modifier_name(m_code)
                if not text:
                    continue

                # 簡易ルール:
                # 1000〜7999 → 前に付ける（接頭語）
                # 8000〜     → 後ろに付ける（接尾語）
                try:
                    n = int(m_code)
                except ValueError:
                    prefixes.append(text)
                    continue

                if 1000 <= n < 8000:
                    prefixes.append(text)
                else:
                    suffixes.append(text)

        full_name = "".join(prefixes) + base_name + "".join(suffixes)

        # カナ表示(オプション) ※修飾語カナはひとまず無視して、傷病名カナだけ付ける
        if self.show_disease_kana and self._get_disease_kana is not None:
            kana = self._get_disease_kana(code)
            if kana:
                full_name = f"{full_name}（{kana}）"

        return full_name
    
    def _split_modifier_codes(self, raw: str, width: int = 4) -> list[str]:
        """
        連結された修飾語コード文字列を width 桁ずつに分割する。

        例: "20572058" -> ["2057", "2058"]

        - 数字以外は除去してから分割
        - 4の倍数でない末尾の端数は無視（必要なら挙動を変えてもOK）
        """
        if not raw:
            return []

        # 数字だけ抜き出す（念のためスペースなどを除去）
        digits = "".join(ch for ch in raw if ch.isdigit())
        if not digits:
            return []

        codes: list[str] = []
        for i in range(0, len(digits), width):
            chunk = digits[i : i + width]
            if len(chunk) == width:
                codes.append(chunk)
        return codes

    # ─────────────────────────────
    # 設定変更時のハンドラ
    # ─────────────────────────────
    def _on_display_option_changed(self, state: int) -> None:
        self.show_disease_kana = self.chk_show_kana.isChecked()
        self.show_disease_date = self.chk_show_date.isChecked()

        if self._current_receipt is not None:
            self._populate_diseases(self._current_receipt)

    def _on_date_format_changed(self, index: int) -> None:
        # 0 = 西暦, 1 = 和暦
        self.date_format_mode = "seireki" if index == 0 else "wareki"
        if self._current_receipt is not None:
            self._populate_diseases(self._current_receipt)

    # ─────────────────────────────
    # ユーティリティ
    # ─────────────────────────────
    def _clear(self) -> None:
        for lbl in [
            self.lbl_year_month,
            self.lbl_receipt_type,
            self.lbl_patient_id,
            self.lbl_name,
            self.lbl_name_kana,
            self.lbl_sex,
            self.lbl_birthday,
            self.lbl_age,
            self.lbl_insurer,
            self.lbl_days,
            self.lbl_total_points,
            self.lbl_calc_points,
            self.lbl_points_diff,
        ]:
            lbl.setText("-")

        if hasattr(self, "qual_widget"):
            self.qual_widget.clear()
        if hasattr(self, "santeibi_widget"):
            self.santeibi_widget.clear()
        if hasattr(self, "preview_widget"):
            self.preview_widget.clear()

        self.raw_view.clear()
        self.disease_table.setRowCount(0)
        self._current_receipt = None

    def _calc_age(self, birthday: Optional[str], year_month: Optional[str]) -> Optional[str]:
        """
        生年月日(YYYYMMDD) と 診療年月(YYYYMM) から概算の満年齢を求める。
        診療年月の１日を基準日にしています。
        """
        if not birthday or not year_month:
            return None
        if len(birthday) != 8 or len(year_month) != 6:
            return None

        try:
            by = int(birthday[0:4])
            bm = int(birthday[4:6])
            bd = int(birthday[6:8])

            ry = int(year_month[0:4])
            rm = int(year_month[4:6])

            bdate = date(by, bm, bd)
            ref   = date(ry, rm, 1)

            age = ref.year - bdate.year - (
                (ref.month, ref.day) < (bdate.month, bdate.day)
            )
        except ValueError:
            return None

        return str(age)

    def _format_ymd_for_display(self, ymd: str) -> str:
        """
        'YYYYMMDD' を設定に応じて表示形式に変換する。

        - 西暦: 2024/10/01
        - 和暦: R06/10/01, H30/12/31 など
        """
        s = (ymd or "").strip()
        if len(s) != 8 or not s.isdigit():
            return s

        year = int(s[0:4])
        month = int(s[4:6])
        day = int(s[6:8])

        # 西暦表示
        if self.date_format_mode == "seireki":
            return f"{year:04d}/{month:02d}/{day:02d}"

        # 和暦表示（ざっくり Heisei / Reiwa のみ）
        era_prefix = ""
        era_year = 0

        # 令和: 2019-05-01 以降
        if (year, month, day) >= (2019, 5, 1):
            era_prefix = "R"
            era_year = year - 2018
        # 平成: 1989-01-08 〜 2019-04-30
        elif (year, month, day) >= (1989, 1, 8):
            era_prefix = "H"
            era_year = year - 1988
        else:
            # それ以前は西暦にフォールバック
            return f"{year:04d}/{month:02d}/{day:02d}"

        return f"{era_prefix}{era_year:02d}/{month:02d}/{day:02d}"

class QualificationWidget(QWidget):
    """
    資格確認等タブ（SN・MF・JDレコードを表示）
    """
    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._build_ui()

    def _build_ui(self) -> None:
        # ルートは縦並び
        root = QVBoxLayout(self)
        root.setContentsMargins(4, 2, 4, 4)
        root.setSpacing(3)

        # ── 上側: SN / MF 用の2列グリッド ─────────────────
        layout = QGridLayout()
        layout.setHorizontalSpacing(8)
        layout.setVerticalSpacing(1)
        root.addLayout(layout)

        # ラベル共通設定ヘルパ
        def make_label(text: str) -> QLabel:
            lbl = QLabel(text, self)
            # 行間を詰めるため、内部マージンをゼロに
            lbl.setMargin(0)
            lbl.setContentsMargins(0, 0, 0, 0)
            return lbl

        def add_pair(row: int, pair_index: int, title: str) -> QLabel:
            col = pair_index * 2
            lbl_title = make_label(title)
            lbl_value = make_label("-")

            layout.addWidget(lbl_title, row, col)
            layout.addWidget(lbl_value, row, col + 1)
            return lbl_value

        # 1行目
        self.lbl_futansha_type   = add_pair(0, 0, "負担者種別")
        self.lbl_kakunin_kbn     = add_pair(0, 1, "確認区分")

        # 2行目
        self.lbl_insurer_all     = add_pair(1, 0, "保険者番号等")
        self.lbl_hihoken_kigo    = add_pair(1, 1, "被保険者証等の記号")

        # 3行目
        self.lbl_hihoken_number  = add_pair(2, 0, "被保険者証等の番号")
        self.lbl_edaban          = add_pair(2, 1, "枝番")

        # 4行目
        self.lbl_jukyusha_number = add_pair(3, 0, "受給者番号")
        self.lbl_madoguchi_kbn   = add_pair(3, 1, "窓口負担額の区分")

        layout.setColumnStretch(0, 0)
        layout.setColumnStretch(1, 3)
        layout.setColumnStretch(2, 0)
        layout.setColumnStretch(3, 3)

        # ── 下側: 受診日等レコード(JD) ─────────────────────
        jd_group = QGroupBox("受診日等レコード (JD)", self)
        jd_layout = QGridLayout(jd_group)
        jd_layout.setContentsMargins(4, 2, 4, 4)
        jd_layout.setHorizontalSpacing(4)
        jd_layout.setVerticalSpacing(1)

        # 1行目: 日付ヘッダ 1〜31
        lbl_day_header = QLabel("日付", jd_group)
        jd_layout.addWidget(lbl_day_header, 0, 0)
        self._jd_day_labels: list[QLabel] = []

        for day in range(1, 32):
            lbl = QLabel(str(day), jd_group)
            lbl.setAlignment(Qt.AlignCenter)
            jd_layout.addWidget(lbl, 0, day)
            self._jd_day_labels.append(lbl)

        # 2行目: 区分（コード→説明）
        self.lbl_jd_futansha = QLabel("区分", jd_group)
        jd_layout.addWidget(self.lbl_jd_futansha, 1, 0)
        self.jd_value_labels: list[QLabel] = []

        for day in range(1, 32):
            lbl = QLabel("", jd_group)
            lbl.setAlignment(Qt.AlignCenter)
            jd_layout.addWidget(lbl, 1, day)
            self.jd_value_labels.append(lbl)

        # 横方向の伸び方（値列を大きめに）
        jd_layout.setColumnStretch(0, 0)
        for day in range(1, 32):
            jd_layout.setColumnStretch(day, 1)

        root.addWidget(jd_group)
        root.addStretch(1)

    # ─────────────────────────────
    # 表示更新系
    # ─────────────────────────────
    def clear(self) -> None:
        for lbl in [
            self.lbl_futansha_type,
            self.lbl_kakunin_kbn,
            self.lbl_insurer_all,
            self.lbl_hihoken_kigo,
            self.lbl_hihoken_number,
            self.lbl_edaban,
            self.lbl_jukyusha_number,
            self.lbl_madoguchi_kbn,
        ]:
            lbl.setText("-")

        if hasattr(self, "lbl_jd_futansha"):
            self.lbl_jd_futansha.setText("区分")

        if hasattr(self, "jd_value_labels"):
            for v in self.jd_value_labels:
                v.setText("")


    def set_from_receipt(self, receipt: Optional[UkeReceipt]) -> None:
        """
        レセプト内の SN / MF / JD レコード1件目を拾って表示する。
        """
        self.clear()

        if receipt is None:
            return

        # --- SN (資格確認レコード) ---------------------------------
        sn_record = next(
            (r for r in receipt.records if r.record_type == "SN"),
            None,
        )

        if sn_record is not None:
            f = sn_record.fields

            def get_sn(i: int) -> str:
                return f[i] if len(f) > i and f[i] else ""

            futansha = get_sn(1).strip()
            kakunin  = get_sn(2).strip()

            self.lbl_futansha_type.setText(
                futansha_type_map().get(futansha, futansha)
            )
            self.lbl_kakunin_kbn.setText(
                kakunin_kubun_map().get(kakunin, kakunin)
            )
            self.lbl_insurer_all.setText(get_sn(3))
            self.lbl_hihoken_kigo.setText(get_sn(4))
            self.lbl_hihoken_number.setText(get_sn(5))
            self.lbl_edaban.setText(get_sn(6))
            self.lbl_jukyusha_number.setText(get_sn(7))
            # ※窓口負担額の区分は MF から取るのでここでは触らない

        # --- MF (窓口負担額レコード) ---------------------------------
        mf_record = next(
            (r for r in receipt.records if r.record_type == "MF"),
            None,
        )

        if mf_record is not None:
            f = mf_record.fields

            def get_mf(i: int) -> str:
                return f[i] if len(f) > i and f[i] else ""

            madoguchi = get_mf(1).strip()  # (2) 窓口負担額の区分
            # 別表31 対応（現状はコード表示だけ）
            self.lbl_madoguchi_kbn.setText(madoguchi)
        # --- JD (受診日等レコード) -----------------------------------
        jd_record = next(
            (r for r in receipt.records if r.record_type == "JD"),
            None,
        )

        if jd_record is not None and hasattr(self, "jd_value_labels"):
            f = jd_record.fields

            # フィールド1 = 負担者種別コード → そのままコードを表示
            futansha_raw = f[1] if len(f) > 1 and f[1] else ""
            if futansha_raw:
                # ★ マスタ展開せず、生のコードのみ
                self.lbl_jd_futansha.setText(futansha_raw)
            else:
                self.lbl_jd_futansha.setText("区分")

            def get_jd_for_day(day: int) -> str:
                idx = day + 1  # fields[2] から 1〜31日
                if len(f) > idx and f[idx]:
                    return f[idx]
                return ""

            for day in range(1, 32):
                raw = get_jd_for_day(day).strip()
                if not raw:
                    disp = ""
                else:
                    disp = jushin_kubun_map().get(raw, raw)
                self.jd_value_labels[day - 1].setText(disp)
        else:
            if hasattr(self, "lbl_jd_futansha"):
                self.lbl_jd_futansha.setText("区分")

class SanteibiWidget(QWidget):
    """
    算定日タブ（ヘッダ + SI / IY / TO / CO レコード一覧）
    """
    def __init__(
        self,
        parent: Optional[QWidget] = None,
        get_shinryo_name: Optional[Callable[[str], str]] = None,
        get_comment_text: Optional[Callable[[str], str]] = None,
    ) -> None:
        super().__init__(parent)
        self._get_shinryo_name = get_shinryo_name
        self._get_comment_text = get_comment_text
        self._build_ui()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(4, 4, 4, 4)
        root.setSpacing(4)

        # ── 上側: 患者情報ヘッダ ─────────────────
        header_group = QGroupBox("算定日ヘッダ情報", self)
        header_layout = QGridLayout(header_group)
        header_layout.setHorizontalSpacing(12)
        header_layout.setVerticalSpacing(2)

        def add_header_item(row: int, col: int, title: str) -> QLabel:
            base_col = col * 2
            lbl_title = QLabel(title, header_group)
            lbl_value = QLabel("-", header_group)
            header_layout.addWidget(lbl_title, row, base_col)
            header_layout.addWidget(lbl_value, row, base_col + 1)
            return lbl_value

        # 1行目
        self.lbl_san_patient_id   = add_header_item(0, 0, "患者番号")
        self.lbl_san_receipt_no   = add_header_item(0, 1, "レセプト番号")
        self.lbl_san_sex          = add_header_item(0, 2, "性別")
        # 2行目
        self.lbl_san_type         = add_header_item(1, 0, "種別")
        self.lbl_san_year_month   = add_header_item(1, 1, "診療年月")
        # 3行目
        self.lbl_san_name         = add_header_item(2, 0, "氏名")
        self.lbl_san_birthday     = add_header_item(2, 1, "生年月日")

        root.addWidget(header_group)

        # ── 下側: SIレコード一覧 ─────────────────
        self.table = QTableWidget(self)
        base_cols = ["診療識別", "負担区分", "診療行為コード", "数量データ", "点数", "回数"]
        day_cols  = [str(d) for d in range(1, 32)]
        headers   = base_cols + day_cols

        self.table.setColumnCount(len(headers))
        self.table.setHorizontalHeaderLabels(headers)
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setSelectionMode(QTableWidget.SingleSelection)

        header = self.table.horizontalHeader()
        # 左側6列は内容に合わせて
        for col in range(6):
            header.setSectionResizeMode(col, QHeaderView.ResizeToContents)
        # 日付列は均等に
        for col in range(6, len(headers)):
            header.setSectionResizeMode(col, QHeaderView.Stretch)

        root.addWidget(self.table)

    # ── クリア ─────────────────
    def clear(self) -> None:
        for lbl in [
            self.lbl_san_patient_id,
            self.lbl_san_receipt_no,
            self.lbl_san_sex,
            self.lbl_san_type,
            self.lbl_san_year_month,
            self.lbl_san_name,
            self.lbl_san_birthday,
        ]:
            lbl.setText("-")

        self.table.setRowCount(0)

    # ── レセプトからセット ─────────────────
    def set_from_receipt(self, receipt: Optional[UkeReceipt]) -> None:
        self.clear()
        if receipt is None or receipt.header is None:
            return

        h = receipt.header

        # ヘッダ情報
        self.lbl_san_patient_id.setText(h.patient_id or "-")
        self.lbl_san_sex.setText(h.sex or "-")
        self.lbl_san_year_month.setText(h.year_month or "-")
        self.lbl_san_name.setText(h.name or "-")
        self.lbl_san_birthday.setText(h.birthday or "-")

        # レセプト番号・種別はモデル側の属性名に合わせて適宜変更
        receipt_no = getattr(h, "receipt_number", None) or getattr(h, "receipt_no", None)
        self.lbl_san_receipt_no.setText(receipt_no or "-")

        rec_type = getattr(h, "receipt_type", None)
        self.lbl_san_type.setText(rec_type or "-")

        # ── SI / IY / TO / CO レコード一覧 ──
        row_idx = 0
        for rec in receipt.records:
            # 対象とするレコード: 診療行為(SI) / 医薬品(IY) / 特定器材(TO) / コメント(CO)
            if rec.record_type not in ("SI", "IY", "TO", "CO"):
                continue

            f = rec.fields
            rec_type = rec.record_type

            def get(i: int) -> str:
                return f[i] if len(f) > i and f[i] else ""

            # 共通構造（SI / IY / TO / CO）
            # 1: 診療識別
            # 2: 負担区分
            # 3: コード（診療行為コード / 医薬品コード / 特定器材コード / コメントコード）
            # 4: 数量データ
            # 5: 点数
            # 6: 回数
            # 7〜37: 算定日情報(1〜31日) を想定
            shikibetsu    = get(1).strip()
            futan         = get(2).strip()
            code          = get(3).strip()
            suuryo        = get(4).strip()
            tensu         = get(5).strip()
            kaisuu        = get(6).strip()

            # コード表示の組み立て
            code_disp = code

            if rec_type == "SI":
                # 診療行為マスタで名称に変換
                if self._get_shinryo_name is not None and code:
                    name = self._get_shinryo_name(code) or ""
                    if name:
                        # 例: "111000110 初診料"
                        code_disp = f"{code} {name}"
            elif rec_type == "CO":
                # コメントマスタでコメント名称に変換
                if self._get_comment_text is not None and code:
                    text = self._get_comment_text(code) or ""
                    if text:
                        code_disp = f"{code} {text}"
            # IY / TO は今のところコードのみ表示だが、
            # 将来 get_iyakuhin_name / get_tokutei_kizai_name を追加すればここで展開可能。

            self.table.insertRow(row_idx)

            base_values = [shikibetsu, futan, code_disp, suuryo, tensu, kaisuu]
            for col, val in enumerate(base_values):
                self.table.setItem(row_idx, col, QTableWidgetItem(val))

            # 日毎の算定日フラグ
            for day in range(1, 32):
                idx = 6 + day  # 1日目→fields[7] と想定
                val = ""
                if len(f) > idx and f[idx]:
                    val = f[idx].strip()
                item = QTableWidgetItem(val)
                item.setTextAlignment(Qt.AlignCenter)
                self.table.setItem(row_idx, 6 + day - 1, item)

            row_idx += 1


# ─────────────────────────────
# レセプト簡易プレビューウィジェット
# ─────────────────────────────
class ReceiptPreviewWidget(QWidget):
    """
    レセプトプレビュータブ用の簡易テキストプレビューワ。
    """
    def __init__(
        self,
        parent: Optional[QWidget] = None,
        get_shinryo_name: Optional[Callable[[str], str]] = None,
        get_comment_text: Optional[Callable[[str], str]] = None,
    ) -> None:
        super().__init__(parent)
        self._get_shinryo_name = get_shinryo_name
        self._get_comment_text = get_comment_text
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(4)
        label = QLabel("レセプト簡易プレビュー", self)
        layout.addWidget(label)
        self.text_edit = QPlainTextEdit(self)
        self.text_edit.setReadOnly(True)
        self.text_edit.setLineWrapMode(QPlainTextEdit.NoWrap)
        # Monospace font if available
        font = QFont("Monospace")
        font.setStyleHint(QFont.Monospace)
        self.text_edit.setFont(font)
        layout.addWidget(self.text_edit)

    def clear(self) -> None:
        self.text_edit.clear()

    def set_from_receipt(self, receipt: Optional[UkeReceipt]) -> None:
        self.clear()
        if receipt is None or getattr(receipt, "header", None) is None:
            return
        h = receipt.header
        lines = []
        # Header
        header_line = f"診療年月: {getattr(h, 'year_month', '-')}, 患者番号: {getattr(h, 'patient_id', '-')}, 氏名: {getattr(h, 'name', '-')}, 性別: {getattr(h, 'sex', '-')}, 生年月日: {getattr(h, 'birthday', '-')}"
        lines.append(header_line)
        lines.append("")
        # 病名
        lines.append("【傷病名】")
        for rec in getattr(receipt, "records", []):
            if getattr(rec, "record_type", "") != "SY":
                continue
            f = rec.fields
            def get(i: int) -> str:
                return f[i] if len(f) > i and f[i] is not None else ""
            code = get(1).strip()
            start_raw = get(2).strip()
            tenki_raw = get(3).strip()
            modifier_raw = get(4).strip()
            name_in_sy = get(5).strip()
            main_flag = get(6).strip()
            mark = "★" if main_flag and main_flag != "0" else "・"
            # For preview, just use name_in_sy if present, otherwise code
            label = name_in_sy if name_in_sy else code
            lines.append(f"{mark} {label}")
        lines.append("")
        # 診療行為
        lines.append("【診療行為】")
        for rec in getattr(receipt, "records", []):
            if getattr(rec, "record_type", "") != "SI":
                continue
            f = rec.fields
            def get(i: int) -> str:
                return f[i] if len(f) > i and f[i] is not None else ""
            shikibetsu = get(1).strip()
            futan = get(2).strip()
            shinryo_code = get(3).strip()
            suuryo = get(4).strip()
            tensu = get(5).strip()
            kaisuu = get(6).strip()
            shinryo_disp = shinryo_code
            if self._get_shinryo_name is not None and shinryo_code:
                name = self._get_shinryo_name(shinryo_code) or ""
                if name:
                    shinryo_disp = f"{shinryo_code} {name}"
            # 算定日
            days = []
            for day in range(1, 32):
                idx = 6 + day
                if len(f) > idx and f[idx]:
                    days.append(str(day))
            days_str = ",".join(days) if days else "-"
            lines.append(f"{shikibetsu}/{futan}  {shinryo_disp}  点数:{tensu}  回数:{kaisuu}  算定日:{days_str}")
        text = "\n".join(lines)
        self.text_edit.setPlainText(text)