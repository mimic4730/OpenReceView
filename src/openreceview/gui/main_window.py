# src/openreceview/gui/main_window.py

from __future__ import annotations

from pathlib import Path
from typing import List, Optional, Dict, Tuple
import csv
import io
import json
from datetime import datetime

import chardet
from PySide6.QtCore import Qt
from PySide6.QtGui import QAction
from PySide6.QtGui import QKeySequence
from PySide6.QtWidgets import (
    QFileDialog,
    QMainWindow,
    QListWidget,
    QPlainTextEdit,
    QSplitter,
    QStatusBar,
    QWidget,
    QTabWidget,
    QInputDialog,
    QMessageBox,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QHBoxLayout,
    QPushButton,
    QComboBox, 
    QLabel,
)
from openreceview.parser.uke_parser import parse_uke_text, group_records_into_receipts
from openreceview.models.uke_record import UkeRecord
from openreceview.models.uke_receipt import UkeReceipt
from openreceview.gui.receipt_summary_widget import ReceiptSummaryWidget
from openreceview.master_loader import (
    load_disease_master,
    load_modifier_master,
    load_shinryo_master,
    load_chouzai_master,
    load_drug_master,
    load_material_master,
    load_ward_master,
    load_comment_master,
    save_master_paths,
)
from openreceview.gui.header_search import (
    HeaderSearchDialog,
    search_receipts_by_header,
)
from openreceview.gui.global_search import GlobalSearchDialog

PREF_NAMES = {
    "01": "北海道", "02": "青森県", "03": "岩手県", "04": "宮城県", "05": "秋田県",
    "06": "山形県", "07": "福島県", "08": "茨城県", "09": "栃木県", "10": "群馬県",
    "11": "埼玉県", "12": "千葉県", "13": "東京都", "14": "神奈川県", "15": "新潟県",
    "16": "富山県", "17": "石川県", "18": "福井県", "19": "山梨県", "20": "長野県",
    "21": "岐阜県", "22": "静岡県", "23": "愛知県", "24": "三重県", "25": "滋賀県",
    "26": "京都府", "27": "大阪府", "28": "兵庫県", "29": "奈良県", "30": "和歌山県",
    "31": "鳥取県", "32": "島根県", "33": "岡山県", "34": "広島県", "35": "山口県",
    "36": "徳島県", "37": "香川県", "38": "愛媛県", "39": "高知県", "40": "福岡県",
    "41": "佐賀県", "42": "長崎県", "43": "熊本県", "44": "大分県", "45": "宮崎県",
    "46": "鹿児島県", "47": "沖縄県",
}

PAYER_TYPES = {
    "1": "社保（支払基金）",
    "2": "国保連合会",
    "3": "国保（市町村）",
    "4": "後期高齢者広域連合",
}

class MainWindow(QMainWindow):
    """
    OpenReceView の最小 GUI 版メインウィンドウ。

    1行 = 1レコードとして扱っています。
    """

    TAB_FACILITY = 0   # 医療機関情報
    TAB_RECORDS  = 1   # レコード一覧
    TAB_RECEIPTS = 2   # レセプト一覧

    # 種別点数情報の集計モード
    GROUP_INSURER = 0              # 広域連合をまとめない（保険者単位）
    GROUP_ALL_WIDE_BY_PREF = 1     # 県単位で広域連合をまとめる
    GROUP_OWN_PREF_ONLY = 2        # 自県のみ県単位でまとめる

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("OpenReceView - レセ電簡易ビューア")
        self.resize(1000, 600)

        # 読み込んだファイルの内容をそのまま保持
        self._current_file: Optional[Path] = None
        self._records: list[UkeRecord] = []
        self._receipts: list[UkeReceipt] = []

        # 傷病名マスタ（コード -> 情報）を保持する
        self._disease_master: dict[str, dict[str, str]] = {}
        # 修飾語マスタ
        self._modifier_name_by_code: dict[str, str] = {}
        self._modifier_kana_by_code: dict[str, str] = {}
        # 診療行為 / 調剤 / 医薬品 / 特定器材 / 病棟 / コメント マスタ
        self._shinryo_master: dict[str, dict[str, str]] = {}
        self._chouzai_master: dict[str, dict[str, str]] = {}
        self._drug_master: dict[str, dict[str, str]] = {}
        self._material_master: dict[str, dict[str, str]] = {}
        self._ward_master: dict[str, dict[str, str]] = {}
        self._comment_master: dict[str, dict[str, str]] = {}  # 将来: コメントコード→テキスト

        # 医療機関（IR）の情報を保持しておく
        self._facility_payer_code: str | None = None   # 支払機関連合種別 (1〜4)
        self._facility_pref_code: str | None = None    # 都道府県コード (01〜47)
        # 総合検索表示をモードレスに
        self._global_search_dialog: GlobalSearchDialog | None = None

        # 種別点数情報の集計モード
        self.points_group_mode = self.GROUP_ALL_WIDE_BY_PREF

        # UI 構築
        self._create_central_widgets()
        self._create_actions()
        self._create_menus()
        self._create_status_bar()
        # レコード検索結果の状態
        self._search_hits: list[int] = []   # ヒットした record のインデックス一覧
        self._search_index: int = -1        # 現在参照中のヒット位置

        # レセプト検索結果の状態
        self._receipt_search_hits: list[int] = []  # ヒットした receipt のインデックス一覧
        self._receipt_search_index: int = -1       # 現在参照中のヒット位置

        # 起動時に前回保存されたマスタパスから自動読み込み
        self._auto_load_masters_from_saved_paths()

    def _auto_load_masters_from_saved_paths(self) -> None:
        """前回保存したマスタファイルパスから、自動的にマスタを読み込む。

        master_loader.save_master_paths() が書き出す JSON を読み取り、
        存在するパスだけを対象に各マスタをロードする。
        読み込みに失敗してもアプリ起動自体は継続する。
        """
        try:
            # save_master_paths 側と同じ想定パス
            config_path = Path.home() / ".openreceview_master_paths.json"
            if not config_path.exists():
                return

            data = json.loads(config_path.read_text(encoding="utf-8"))
        except Exception:
            # 設定ファイル破損などは無視
            return

        # helper: パスリストを Path に変換し、実在するものだけ返す
        def _existing_paths(key: str) -> list[Path]:
            raw_list = data.get(key) or []
            paths: list[Path] = []
            for p in raw_list:
                try:
                    path_obj = Path(p)
                except Exception:
                    continue
                if path_obj.is_file():
                    paths.append(path_obj)
            return paths

        # 各マスタを順次ロード（存在するものだけ）
        try:
            disease_paths = _existing_paths("disease")
            if disease_paths:
                self._disease_master = load_disease_master(disease_paths)
                self._update_master_status("disease")
        except Exception:
            pass

        try:
            modifier_paths = _existing_paths("modifier")
            if modifier_paths:
                name_by_code, kana_by_code = load_modifier_master(modifier_paths)
                self._modifier_name_by_code = name_by_code
                self._modifier_kana_by_code = kana_by_code
                self._update_master_status("modifier")
        except Exception:
            pass

        try:
            shinryo_paths = _existing_paths("shinryo")
            if shinryo_paths:
                self._shinryo_master = load_shinryo_master(shinryo_paths)
                self._update_master_status("shinryo")
        except Exception:
            pass

        try:
            chouzai_paths = _existing_paths("chouzai")
            if chouzai_paths:
                self._chouzai_master = load_chouzai_master(chouzai_paths)
                self._update_master_status("chouzai")
        except Exception:
            pass

        try:
            drug_paths = _existing_paths("drug")
            if drug_paths:
                self._drug_master = load_drug_master(drug_paths)
                self._update_master_status("drug")
        except Exception:
            pass

        try:
            material_paths = _existing_paths("material")
            if material_paths:
                self._material_master = load_material_master(material_paths)
                self._update_master_status("material")
        except Exception:
            pass

        try:
            ward_paths = _existing_paths("ward")
            if ward_paths:
                self._ward_master = load_ward_master(ward_paths)
                self._update_master_status("ward")
        except Exception:
            pass

        try:
            comment_paths = _existing_paths("comment")
            if comment_paths:
                self._comment_master = load_comment_master(comment_paths)
                self._update_master_status("comment")
        except Exception:
            pass

        # どれか一つでも読めていれば、ステータスバーに簡単なメッセージを出す
        if any([
            self._disease_master,
            self._modifier_name_by_code,
            self._shinryo_master,
            self._chouzai_master,
            self._drug_master,
            self._material_master,
            self._ward_master,
            self._comment_master,
        ]):
            try:
                self.statusBar().showMessage("前回のマスタ設定を自動読み込みしました。")
            except Exception:
                # statusBar 未初期化のタイミングでは何もしない
                pass

    # ─────────────────────────────
    # UI 構築
    # ─────────────────────────────
    def _create_central_widgets(self) -> None:
        """
        中央領域：
          - タブ0: 医療機関情報（IR 行から作成）
          - タブ1: レコード一覧
          - タブ2: レセプト一覧
        """
        self.tabs = QTabWidget(self)

        # ── タブ0: 医療機関情報 ─────────────────────
        facility_splitter = QSplitter(Qt.Horizontal, self)

        self.facility_tree = QTreeWidget(facility_splitter)
        self.facility_tree.setColumnCount(7)
        self.facility_tree.setHeaderLabels([
            "種別支払機関",
            "都道府県",
            "医療機関コード",
            "診療科",
            "医療機関名称",
            "請求年月",
            "VOL",
        ])
        self.facility_tree.itemClicked.connect(self._on_facility_item_clicked)

        # 右ペイン：レセプト詳細用のウィジェット

        self.facility_detail = ReceiptSummaryWidget(
            facility_splitter,
            get_disease_name=self._get_disease_name,
            get_disease_kana=self._get_disease_kana,
            get_modifier_name=self.get_modifier_name,
            get_modifier_kana=self.get_modifier_kana,
            get_shinryo_name=self.get_shinryo_name,
            get_comment_text=self.get_comment_text,
            get_iyakuhin_name=self.get_iyakuhin_name,
            get_tokutei_kizai_name=self.get_tokutei_kizai_name,
            is_disease_abolished=self.is_disease_abolished,
            is_shinryo_abolished=self.is_shinryo_abolished,
        )

        facility_splitter.setStretchFactor(0, 1)
        facility_splitter.setStretchFactor(1, 2)

        self.tabs.addTab(facility_splitter, "医療機関情報")

        # ── タブ1: レコード一覧 ─────────────────────
        record_splitter = QSplitter(Qt.Horizontal, self)

        self.record_list = QListWidget(record_splitter)
        self.record_list.setSelectionMode(QListWidget.SingleSelection)
        self.record_list.currentRowChanged.connect(self._on_record_selected)

        self.raw_view = QPlainTextEdit(record_splitter)
        self.raw_view.setReadOnly(True)
        self.raw_view.setLineWrapMode(QPlainTextEdit.NoWrap)
        self.raw_view.setPlaceholderText("ここに選択したレコードの内容が表示されます")

        record_splitter.addWidget(self.record_list)
        record_splitter.addWidget(self.raw_view)
        record_splitter.setStretchFactor(0, 1)
        record_splitter.setStretchFactor(1, 3)

        self.tabs.addTab(record_splitter, "レコード一覧")

        # ── タブ2: レセプト一覧 ─────────────────────
        receipt_splitter = QSplitter(Qt.Horizontal, self)

        self.receipt_list = QListWidget(receipt_splitter)
        self.receipt_list.setSelectionMode(QListWidget.SingleSelection)
        self.receipt_list.currentRowChanged.connect(self._on_receipt_selected)

        self.receipt_detail = ReceiptSummaryWidget(
            receipt_splitter,
            get_disease_name=self._get_disease_name,
            get_disease_kana=self._get_disease_kana,
            get_modifier_name=self.get_modifier_name,
            get_modifier_kana=self.get_modifier_kana,
            get_shinryo_name=self.get_shinryo_name,
            get_comment_text=self.get_comment_text,
            get_iyakuhin_name=self.get_iyakuhin_name,
            get_tokutei_kizai_name=self.get_tokutei_kizai_name,
            is_disease_abolished=self.is_disease_abolished,
            is_shinryo_abolished=self.is_shinryo_abolished,
        )

        receipt_splitter.addWidget(self.receipt_list)
        receipt_splitter.addWidget(self.receipt_detail)
        receipt_splitter.setStretchFactor(0, 1)
        receipt_splitter.setStretchFactor(1, 3)

        self.tabs.addTab(receipt_splitter, "レセプト一覧")

        self.setCentralWidget(self.tabs)

        # ── タブ3: 種別点数情報 ─────────────────────
        points_root = QWidget(self)
        points_layout = QVBoxLayout(points_root)
        points_layout.setContentsMargins(4, 4, 4, 4)
        points_layout.setSpacing(4)

        # 上部: 操作用ボタン（トグル）行
        toolbar = QHBoxLayout()
        toolbar.setContentsMargins(0, 0, 0, 0)
        toolbar.setSpacing(8)

        self.points_toggle_btn = QPushButton("すべて展開", points_root)
        self.points_toggle_btn.setCheckable(True)
        self.points_toggle_btn.toggled.connect(self._on_points_toggle)

        toolbar.addWidget(self.points_toggle_btn)

        # 集計モード選択コンボボックス
        self.points_group_combo = QComboBox(points_root)
        self.points_group_combo.addItems([
            "広域連合をまとめない（保険者単位）",
            "県単位で広域連合をまとめる",
            "自県の広域連合のみまとめる",
        ])
        self.points_group_combo.setCurrentIndex(self.points_group_mode)
        self.points_group_combo.currentIndexChanged.connect(self._on_points_group_changed)
        toolbar.addWidget(self.points_group_combo)

        # 合計人数・件数・点数表示用ラベル（種別点数情報タブ専用）
        self.points_total_label = QLabel("", points_root)
        # 必要ならフォントを少し太くするなども可
        font = self.points_total_label.font()
        font.setBold(True)
        self.points_total_label.setFont(font)
        toolbar.addWidget(self.points_total_label)

        toolbar.addStretch(1)
        points_layout.addLayout(toolbar)

        # 下部: ツリー本体
        self.points_tree = QTreeWidget(points_root)
        self.points_tree.setColumnCount(6)
        self.points_tree.setHeaderLabels([
            "保険者番号",
            "レセプト種別",
            "診療年月",
            "件数",
            "合計点数",
            "内訳",
        ])

        points_layout.addWidget(self.points_tree)

        self.tabs.addTab(points_root, "種別点数情報")

    def _create_actions(self) -> None:
        # ファイルを開く
        self.open_action = QAction("開く(&O)...", self)
        self.open_action.setShortcut("Ctrl+O")
        self.open_action.triggered.connect(self._on_open_file)

        # 終了
        self.exit_action = QAction("終了(&Q)", self)
        self.exit_action.setShortcut("Ctrl+Q")
        self.exit_action.triggered.connect(self.close)

        # レコード検索
        self.search_action = QAction("検索(&F)...", self)
        self.search_action.setShortcut(QKeySequence.Find)  # Ctrl+F
        self.search_action.triggered.connect(self._on_search)

        # レコード 次を検索
        self.search_next_action = QAction("次を検索(&N)", self)
        self.search_next_action.setShortcut(QKeySequence.FindNext)  # 通常 F3
        self.search_next_action.triggered.connect(self._on_search_next)

        # レセプト検索
        self.receipt_search_action = QAction("レセプト検索(&R)...", self)
        # Ctrl+Shift+F にしておく（お好みで変更可）
        self.receipt_search_action.setShortcut("Ctrl+Shift+F")
        self.receipt_search_action.triggered.connect(self._on_receipt_search)

        # レセプト 次を検索
        self.receipt_search_next_action = QAction("レセプト次を検索(&X)", self)
        # Ctrl+Shift+N にしておく
        self.receipt_search_next_action.setShortcut("Ctrl+Shift+N")
        self.receipt_search_next_action.triggered.connect(self._on_receipt_search_next)

        # ヘッダ検索（レセプトヘッダ項目を対象にした検索）
        self.header_search_action = QAction("ヘッダ検索(&H)...", self)
        # お好みでショートカットは変更可（ここでは Ctrl+H とする）
        self.header_search_action.setShortcut("Ctrl+H")
        self.header_search_action.triggered.connect(self._on_header_search)

        # 詳細検索（グローバル検索ダイアログ）
        self.global_search_action = QAction("詳細検索(&S)...", self)
        # 既存のショートカットと被らないように Ctrl+Alt+F を割り当て
        self.global_search_action.setShortcut("Ctrl+Alt+F")
        self.global_search_action.triggered.connect(self._on_global_search)

        # 傷病名マスタ読込
        self.load_disease_master_action = QAction("傷病名マスタ読込(&D)...", self)
        self.load_disease_master_action.triggered.connect(self._on_load_disease_master)

        # 修飾語マスタ読込
        self.load_modifier_master_action = QAction("修飾語マスタ読込(&Z)...", self)
        self.load_modifier_master_action.triggered.connect(self._on_load_modifier_master)

        # 診療行為マスタ読込
        self.load_shinryo_master_action = QAction("診療行為マスタ読込(&S)...", self)
        self.load_shinryo_master_action.triggered.connect(self._on_load_shinryo_master)

        # 調剤行為マスタ読込
        self.load_chouzai_master_action = QAction("調剤行為マスタ読込(&J)...", self)
        self.load_chouzai_master_action.triggered.connect(self._on_load_chouzai_master)

        # 医薬品マスタ読込
        self.load_drug_master_action = QAction("医薬品マスタ読込(&Y)...", self)
        self.load_drug_master_action.triggered.connect(self._on_load_drug_master)

        # 特定器材マスタ読込
        self.load_material_master_action = QAction("特定器材マスタ読込(&T)...", self)
        self.load_material_master_action.triggered.connect(self._on_load_material_master)

        # 病棟コードマスタ読込
        self.load_ward_master_action = QAction("病棟コードマスタ読込(&B)...", self)
        self.load_ward_master_action.triggered.connect(self._on_load_ward_master)

        # コメントマスタ読込
        self.load_comment_master_action = QAction("コメントマスタ読込(&C)...", self)
        self.load_comment_master_action.triggered.connect(self._on_load_comment_master)
        
        # ─────────────────────────────
        # マスタ読込状況表示用（メニューに出すだけの読み取り専用アクション）
        # ─────────────────────────────
        self.master_status_disease  = QAction("傷病名: 未読込", self)
        self.master_status_modifier = QAction("修飾語: 未読込", self)
        self.master_status_shinryo  = QAction("診療行為: 未読込", self)
        self.master_status_chouzai  = QAction("調剤行為: 未読込", self)
        self.master_status_drug     = QAction("医薬品: 未読込", self)
        self.master_status_material = QAction("特定器材: 未読込", self)
        self.master_status_ward     = QAction("病棟コード: 未読込", self)
        self.master_status_comment  = QAction("コメント: 未読込", self)

        # メニューからクリックされないように無効化
        for act in [
            self.master_status_disease,
            self.master_status_modifier,
            self.master_status_shinryo,
            self.master_status_chouzai,
            self.master_status_drug,
            self.master_status_material,
            self.master_status_ward,
            self.master_status_comment,
        ]:
            act.setEnabled(False)

    def _create_menus(self) -> None:
        menubar = self.menuBar()

        file_menu = menubar.addMenu("ファイル(&F)")
        file_menu.addAction(self.open_action)
        file_menu.addSeparator()
        file_menu.addAction(self.exit_action)

        # 表示メニュー（検索系）
        view_menu = menubar.addMenu("表示(&V)")
        # ── レコード単位の簡易検索 ──
        view_menu.addAction(self.search_action)
        view_menu.addAction(self.search_next_action)
        view_menu.addSeparator()
        # ── ヘッダ検索 ──
        view_menu.addAction(self.header_search_action)
        view_menu.addSeparator()
        # ── 詳細検索（専用ウインドウ） ──
        view_menu.addAction(self.global_search_action)
        view_menu.addSeparator()
        # ── レセプト単位の全文検索 ──
        view_menu.addAction(self.receipt_search_action)
        view_menu.addAction(self.receipt_search_next_action)

        # マスタメニュー
        master_menu = menubar.addMenu("マスタ(&M)")
        master_menu.addAction(self.load_disease_master_action)
        master_menu.addAction(self.load_modifier_master_action)
        master_menu.addSeparator()
        master_menu.addAction(self.load_shinryo_master_action)
        master_menu.addAction(self.load_chouzai_master_action)
        master_menu.addAction(self.load_drug_master_action)
        master_menu.addAction(self.load_material_master_action)
        master_menu.addAction(self.load_ward_master_action)
        master_menu.addAction(self.load_comment_master_action)
        
        # 読み込み状況表示（クリック不可のステータス行）
        master_menu.addSeparator()
        master_menu.addAction(self.master_status_disease)
        master_menu.addAction(self.master_status_modifier)
        master_menu.addAction(self.master_status_shinryo)
        master_menu.addAction(self.master_status_chouzai)
        master_menu.addAction(self.master_status_drug)
        master_menu.addAction(self.master_status_material)
        master_menu.addAction(self.master_status_ward)
        master_menu.addAction(self.master_status_comment)        

    def _create_status_bar(self) -> None:
        status = QStatusBar(self)
        self.setStatusBar(status)
        self.statusBar().showMessage("UKE/CSVファイルを開いてください (Ctrl+O)")

    def _update_master_status(self, key: str) -> None:
        """
        マスタ読込時に、メニュー上の「読み込み済み・日時」を更新する共通ヘルパー。
        key は "disease" / "modifier" / "shinryo" / "chouzai" / "drug" /
               "material" / "ward" / "comment" を想定。
        """
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M")

        label_map = {
            "disease":  "傷病名",
            "modifier": "修飾語",
            "shinryo":  "診療行為",
            "chouzai":  "調剤行為",
            "drug":     "医薬品",
            "material": "特定器材",
            "ward":     "病棟コード",
            "comment":  "コメント",
        }
        action_map = {
            "disease":  self.master_status_disease,
            "modifier": self.master_status_modifier,
            "shinryo":  self.master_status_shinryo,
            "chouzai":  self.master_status_chouzai,
            "drug":     self.master_status_drug,
            "material": self.master_status_material,
            "ward":     self.master_status_ward,
            "comment":  self.master_status_comment,
        }

        action = action_map.get(key)
        if action is None:
            return

        label = label_map.get(key, key)
        action.setText(f"{label}: 読込済み ({now_str})")

    # ─────────────────────────────
    # ファイル読み込み
    # ─────────────────────────────
    def _on_open_file(self) -> None:
        """
        [ファイル]→[開く] が押されたときに呼ばれる。
        """
        path_str, _ = QFileDialog.getOpenFileName(
            self,
            "レセ電ファイルを開く",
            "",
            "テキストファイル (*.txt *.csv *.uke);;すべてのファイル (*.*)",
        )
        if not path_str:
            return

        path = Path(path_str)
        self._load_text_file(path)

    def _load_text_file(self, path: Path) -> None:
        """
        テキストファイルを読み込み、行一覧とレセプト一覧にセットする。
        """
        try:
            raw = path.read_bytes()
        except OSError as e:
            self.statusBar().showMessage(f"ファイル読み込みエラー: {e}")
            return

        candidate_encodings = ["cp932", "euc_jp", "utf-8"]

        best_text: str | None = None
        best_encoding: str | None = None
        best_score: float = float("-inf")

        for enc in candidate_encodings:
            try:
                text = raw.decode(enc)
            except UnicodeDecodeError:
                continue

            num_jp = sum(
                1
                for ch in text
                if (
                    "\u3040" <= ch <= "\u30ff"
                    or "\u4e00" <= ch <= "\u9fff"
                )
            )
            num_replacement = text.count("\ufffd")
            num_ctrl = sum(
                1 for ch in text if ord(ch) < 0x20 and ch not in "\r\n\t"
            )

            score = num_jp - (num_replacement * 10 + num_ctrl * 2)

            if score > best_score:
                best_score = score
                best_text = text
                best_encoding = enc

        if best_text is None or best_encoding is None:
            best_encoding = "cp932"
            best_text = raw.decode(best_encoding, errors="replace")

        self._current_file = path

        # ★ ここでパーサ → レセプト構築
        self._records = parse_uke_text(best_text)
        self._receipts = group_records_into_receipts(self._records)

        self._populate_record_list()
        self._populate_receipt_list()
        self._populate_facility_info()
        self._populate_points_summary()

        self.statusBar().showMessage(
            f"{path.name} を読み込みました "
            f"(選択エンコーディング: {best_encoding}, スコア: {best_score:.0f})"
        )
        
        if self._global_search_dialog is not None:
            # GlobalSearchDialog 側に「レセプト一覧を差し替えるメソッド」を用意しておく想定
            self._global_search_dialog.update_receipts(self._receipts)

    def _populate_record_list(self) -> None:
        """
        読み込んだレコード一覧を QListWidget に流し込む。
        1レコード = 1行として、
        「行番号」と「レコード種別」を先頭に表示する。
        """
        self.record_list.clear()
        self.raw_view.clear()

        for rec in self._records:
            summary = rec.raw.replace("\t", "    ").strip()
            if len(summary) > 40:
                summary = summary[:40] + "…"

            item_text = f"{rec.line_no:05d} [{rec.record_type}] {summary}"
            self.record_list.addItem(item_text)

        if self._records:
            self.record_list.setCurrentRow(0)

    def _populate_receipt_list(self) -> None:
        self.receipt_list.clear()
        # ★ ReceiptSummaryWidget 側をクリア
        self.receipt_detail.set_receipt(None)

        for receipt in self._receipts:
            h = receipt.header
            if h:
                pid = h.patient_id or "?"
                ym  = h.year_month or "?"
                name = h.name or ""
            else:
                pid = "?"
                ym = "?"
                name = ""

            if len(name) > 10:
                name_disp = name[:10] + "…"
            else:
                name_disp = name

            item_text = (
                f"{receipt.index:05d} "
                f"患者番号={pid} 診療年月={ym} "
                f"氏名={name_disp} "
                f"(行 {receipt.start_line}～{receipt.end_line}, "
                f"{len(receipt.records)}レコード)"
            )
            self.receipt_list.addItem(item_text)

        if self._receipts:
            self.receipt_list.setCurrentRow(0)

    def _populate_facility_info(self) -> None:
        """
        IR レコードから医療機関情報を抽出し、facility_tree に表示する。

        構造:
          ルート: 医療機関 (ファイル全体)
            ├─ IR 医療機関情報
            │    ├─ 種別支払機関 : ...
            │    ├─ 都道府県     : ...
            │    ├─ 医療機関コード: ...
            │    ├─ 医療機関名称 : ...
            │    ├─ 診療科       : ...
            │    ├─ 請求年月     : ...
            │    └─ VOL          : ...
            └─ RE レセプト一覧
                 ├─ 00001  患者番号=...  氏名=...  診療年月=...
                 ├─ 00002  ...
                 └─ ...
        """
        self.facility_tree.clear()

        # IR レコードを探す（通常ファイル先頭付近に 1 件）
        ir_rec = next((r for r in self._records if r.record_type == "IR"), None)
        if ir_rec is None:
            return

        f = ir_rec.fields

        def get(i: int) -> str:
            return f[i] if len(f) > i and f[i] is not None else ""

        payer_code = get(1)      # 1:支払機関連合種別
        pref_code = get(2)       # 2:都道府県コード
        # 後で集計モードで使うために保存
        self._facility_payer_code = payer_code or ""
        self._facility_pref_code = pref_code or ""
        inst_code = get(4)       # 4:医療機関コード
        dept      = get(5)       # 5:診療科（なければ空）
        inst_name = get(6)       # 6:医療機関名称
        claim_ym  = get(7)       # 7:請求年月(YYYYMM)
        vol       = get(8)       # 8:VOL

        payer_text = PAYER_TYPES.get(payer_code, payer_code or "-")
        pref_text  = PREF_NAMES.get(pref_code.zfill(2), pref_code or "-")
        dept_text  = dept if dept else "なし"
        ym_text    = self._format_claim_ym_jp(claim_ym) if claim_ym else "-"

        # ── ルート（医療機関）行 ─────────────────────
        root_item = QTreeWidgetItem(self.facility_tree)
        root_item.setText(0, payer_text)
        root_item.setText(1, pref_text)
        root_item.setText(2, inst_code or "-")
        root_item.setText(3, dept_text)
        root_item.setText(4, inst_name or "-")
        root_item.setText(5, ym_text)
        root_item.setText(6, vol or "-")

        # ── 子①: IR 医療機関情報 ノード ─────────────────
        ir_node = QTreeWidgetItem(root_item)
        ir_node.setText(0, "IR 医療機関情報")

        def add_kv(parent: QTreeWidgetItem, label: str, value: str) -> None:
            """
            key/value を縦に並べる行を追加する。
            見た目をわかりやすくするため、列3を「項目名」、列4を「値」として使う。
            """
            item = QTreeWidgetItem(parent)
            item.setText(3, label)
            item.setText(4, value or "-")

        add_kv(ir_node, "種別支払機関", payer_text)
        add_kv(ir_node, "都道府県", pref_text)
        add_kv(ir_node, "医療機関コード", inst_code or "-")
        add_kv(ir_node, "医療機関名称", inst_name or "-")
        add_kv(ir_node, "診療科", dept_text)
        add_kv(ir_node, "請求年月", ym_text)
        add_kv(ir_node, "VOL", vol or "-")

        # ── 子②: RE レセプト一覧 ノード ─────────────────
        re_node = QTreeWidgetItem(root_item)
        re_node.setText(0, "RE レセプト一覧")
        re_node.setText(1, f"{len(self._receipts)} 件")

        for receipt in self._receipts:
            h = receipt.header
            item = QTreeWidgetItem(re_node)
            item.setText(0, f"{receipt.index:05d}")  # レセプト通し番号
            # ★ レセプト一覧タブの行インデックスを UserRole に保持（0始まり）
            item.setData(0, Qt.UserRole, receipt.index - 1)

            if h:
                # 患者番号 / 氏名 / 診療年月 を適当に並べる
                item.setText(1, h.patient_id or "")
                item.setText(2, h.name or "")
                item.setText(3, h.year_month or "")
            else:
                item.setText(1, "")
                item.setText(2, "")
                item.setText(3, "")

        # 展開＆列幅調整
        self.facility_tree.expandAll()
        self.facility_tree.resizeColumnToContents(0)
        self.facility_tree.resizeColumnToContents(1)
        self.facility_tree.resizeColumnToContents(3)
        self.facility_tree.resizeColumnToContents(4)

    def _populate_points_summary(self) -> None:
        """
        HO レコードとヘッダ情報から「種別点数情報」を構築し、
        self.points_tree に表示する。

        構造:
          ルート: グループ（集計モードに応じて）
            - 列: 保険者番号 or 県名 など / 件数 / 合計点数
            子: (レセプト種別 × 診療年月) ごとの内訳
        """
        self.points_tree.clear()
        from collections import defaultdict

        # group_id -> 集計
        #   label: 画面に表示する名称（保険者番号 or 県名＋広域連合）
        #   total_count: レセプト件数
        #   total_points: 合計点数
        #   details[(receipt_type, year_month)] -> {count, points}
        summary: dict[str, dict] = {}

        # 全体の合計（人数 / 件数 / 点数）
        total_receipt_count = 0           # 合計件数（レセプト件数）
        total_points_all    = 0           # 合計点数
        unique_patient_ids  = set()       # 患者番号のユニーク数 = 合計人数


        for receipt in self._receipts:
            h = receipt.header
            if h is None:
                continue

            # HO レコードを探す
            ho = next((r for r in receipt.records if r.record_type == "HO"), None)
            if ho is None:
                continue

            f = ho.fields

            def get(i: int) -> str:
                return f[i] if len(f) > i and f[i] is not None else ""

            # HO の保険者番号
            insurer_raw = get(1) or "-"
            # HO,保険者番号,,番号,診療実日数,合計点数,...
            total_points_str = get(5)
            try:
                points = int(total_points_str.replace(",", "")) if total_points_str else 0
            except ValueError:
                points = 0

            rtype = h.receipt_type or ""   # レセプト種別
            ym    = h.year_month or ""     # 診療年月
            pid   = (getattr(h, "patient_id", None) or "").strip()

            # 全体の合計を更新
            total_receipt_count += 1
            total_points_all    += points
            if pid:
                unique_patient_ids.add(pid)

            # HO の保険者番号だけを使ってグループを決定
            group_id, label = self._points_group_key(insurer_raw)

            if group_id not in summary:
                summary[group_id] = {
                    "label": label,
                    "total_count": 0,
                    "total_points": 0,
                    "details": defaultdict(lambda: {"count": 0, "points": 0}),
                }

            entry = summary[group_id]
            entry["total_count"] += 1
            entry["total_points"] += points

            key = (rtype, ym)
            entry["details"][key]["count"]  += 1
            entry["details"][key]["points"] += points

        # ツリーに反映
        for group_id in sorted(summary.keys()):
            entry = summary[group_id]
            total_count  = entry["total_count"]
            total_points = entry["total_points"]

            root = QTreeWidgetItem(self.points_tree)
            root.setText(0, entry["label"])
            root.setText(3, str(total_count))
            root.setText(4, f"{total_points:,}")

            # 子: レセプト種別 × 診療年月ごとの内訳
            for (rtype, ym), det in sorted(entry["details"].items()):
                child = QTreeWidgetItem(root)
                child.setText(1, rtype or "")
                child.setText(2, ym or "")
                child.setText(3, str(det["count"]))
                child.setText(4, f"{det['points']:,}")
                child.setText(5, "合算")  # 内訳の詳細分類は今は「合算」のまま

        self.points_tree.expandAll()
        self.points_toggle_btn.setChecked(True)
        self.points_toggle_btn.setText("すべて折りたたみ")

        # ラベルに「合計人数 / 合計件数 / 合計点数」を表示
        if hasattr(self, "points_total_label") and self.points_total_label is not None:
            total_people = len(unique_patient_ids)
            if total_receipt_count == 0 and total_points_all == 0 and total_people == 0:
                # データがない場合は空表示
                self.points_total_label.setText("")
            else:
                self.points_total_label.setText(
                    f"合計人数(実人数)：{total_people:,}　"
                    f"合計件数(レセプト件数)：{total_receipt_count:,}　"
                    f"合計点数：{total_points_all:,}"
                )

    # ─────────────────────────────
    # イベントハンドラ
    # ─────────────────────────────
    def _on_record_selected(self, row: int) -> None:
        """
        左リストで選択された行が変わったときに呼ばれる。
        """
        if row < 0 or row >= len(self._records):
            self.raw_view.clear()
            return

        rec = self._records[row]

        lines: list[str] = []
        lines.append(f"行番号: {rec.line_no}")
        lines.append(f"レコード種別: {rec.record_type}")
        lines.append(f"フィールド数: {len(rec.fields)}")
        lines.append("")
        lines.append("[生データ]")
        lines.append(rec.raw)
        lines.append("")
        lines.append("[フィールド分解]")
        for idx, field in enumerate(rec.fields, start=1):
            lines.append(f"{idx:02d}: {field}")

        self.raw_view.setPlainText("\n".join(lines))

        self.statusBar().showMessage(
            f"{rec.line_no} 行目（種別: {rec.record_type}）を表示中 / 全 {len(self._records)} 行"
        )

    def _on_receipt_selected(self, row: int) -> None:
        """
        レセプト一覧タブで選択が変わったときに呼ばれる。
        """
        if row < 0 or row >= len(self._receipts):
            self.receipt_detail.set_receipt(None)
            return

        receipt = self._receipts[row]
        self.receipt_detail.set_receipt(receipt)

        h = receipt.header
        if h:
            msg = (
                f"レセプト {receipt.index} "
                f"(患者番号={h.patient_id or '-'}, 診療年月={h.year_month or '-'}) を表示中"
            )
        else:
            msg = f"レセプト {receipt.index} を表示中"

        self.statusBar().showMessage(msg)

    def _on_facility_item_clicked(self, item: QTreeWidgetItem, column: int) -> None:
        parent = item.parent()
        if parent is None:
            return

        # 「RE レセプト一覧」の直下の行だけを対象
        if parent.text(0) != "RE レセプト一覧":
            return

        data = item.data(0, Qt.UserRole)
        if data is None:
            return

        try:
            idx = int(data)
        except (TypeError, ValueError):
            return

        if idx < 0 or idx >= len(self._receipts):
            return

        # ★ 1) 医療機関情報タブ右ペインの詳細を更新
        receipt = self._receipts[idx]
        self.facility_detail.set_receipt(receipt)

        # ★ 2) バックグラウンドでレセプト一覧タブも同期しておく（任意）
        self.receipt_list.setCurrentRow(idx)

        h = receipt.header
        if h:
            self.statusBar().showMessage(
                f"[医療機関情報] レセプト {receipt.index} "
                f"(患者番号={h.patient_id or '-'}, 診療年月={h.year_month or '-'}) を表示中"
            )
        else:
            self.statusBar().showMessage(
                f"[医療機関情報] レセプト {receipt.index} を表示中"
            )

    def _on_points_toggle(self, checked: bool) -> None:
        """
        種別点数情報タブの「すべて展開」トグルボタン。
        """
        if checked:
            self.points_tree.expandAll()
            self.points_toggle_btn.setText("すべて折りたたみ")
        else:
            self.points_tree.collapseAll()
            self.points_toggle_btn.setText("すべて展開")

    def _on_points_group_changed(self, index: int) -> None:
        """
        種別点数情報タブの集計モードコンボボックスが変更されたとき。
        """
        self.points_group_mode = index
        # すでにレセプトが読み込まれているなら再集計
        if self._receipts:
            self._populate_points_summary()

    # ─────────────────────────────
    # マスタ読み込みハンドラ
    # ─────────────────────────────
    def _on_load_disease_master(self) -> None:
        paths, _ = QFileDialog.getOpenFileNames(
            self,
            "傷病名マスタファイルを選択（b / hb をまとめて選択可）",
            "",
            "テキストファイル (*.txt *.csv);;すべてのファイル (*.*)",
        )
        if not paths:
            return

        try:
            path_objs = [Path(p) for p in paths]
            master = load_disease_master(path_objs)
        except Exception as e:
            QMessageBox.warning(
                self,
                "傷病名マスタ読み込みエラー",
                f"傷病名マスタファイルの読み込みに失敗しました。\n\nエラー: {e}",
            )
            return

        # 読み込んだ結果を自分のフィールドに反映
        self._disease_master = master
        save_master_paths("disease", path_objs)
        self._update_master_status("disease")

        QMessageBox.information(
            self,
            "傷病名マスタ読込",
            f"傷病名マスタを読み込みました。\n"
            f"ファイル数: {len(paths)}\n"
            f"傷病名コード数: {len(self._disease_master):,}",
        )
        self.statusBar().showMessage(
            f"傷病名マスタ読込完了: {len(self._disease_master):,} コード"
        )

    def _on_load_modifier_master(self) -> None:
        paths, _ = QFileDialog.getOpenFileNames(
            self,
            "修飾語マスタファイルを選択（Z マスタをまとめて選択可）",
            "",
            "テキストファイル (*.txt *.csv);;すべてのファイル (*.*)",
        )
        if not paths:
            return

        try:
            path_objs = [Path(p) for p in paths]
            name_by_code, kana_by_code = load_modifier_master(path_objs)
        except Exception as e:
            QMessageBox.warning(
                self,
                "修飾語マスタ読み込みエラー",
                f"修飾語マスタファイルの読み込みに失敗しました。\n\nエラー: {e}",
            )
            return

        self._modifier_name_by_code = name_by_code
        self._modifier_kana_by_code = kana_by_code
        save_master_paths("modifier", path_objs)
        self._update_master_status("modifier")

        QMessageBox.information(
            self,
            "修飾語マスタ読込",
            f"修飾語マスタを読み込みました。\n"
            f"ファイル数: {len(paths)}\n"
            f"修飾語コード数: {len(self._modifier_name_by_code):,}",
        )
        self.statusBar().showMessage(
            f"修飾語マスタ読込完了: {len(self._modifier_name_by_code):,} コード"
        )

    def _on_load_shinryo_master(self) -> None:
        """
        [マスタ] → [診療行為マスタ] の読込処理。
        """
        paths, _ = QFileDialog.getOpenFileNames(
            self,
            "診療行為マスタファイルを選択（S マスタをまとめて選択可）",
            "",
            "テキストファイル (*.txt *.csv);;すべてのファイル (*.*)",
        )
        if not paths:
            return

        try:
            path_objs = [Path(p) for p in paths]
            master = load_shinryo_master(path_objs)
        except Exception as e:
            QMessageBox.warning(
                self,
                "診療行為マスタ読み込みエラー",
                f"診療行為マスタファイルの読み込みに失敗しました。\n\nエラー: {e}",
            )
            return

        self._shinryo_master = master
        save_master_paths("shinryo", path_objs)
        self._update_master_status("shinryo")

        QMessageBox.information(
            self,
            "診療行為マスタ読込",
            f"診療行為マスタを読み込みました。\n"
            f"ファイル数: {len(paths)}\n"
            f"診療行為コード数: {len(self._shinryo_master):,}",
        )
        self.statusBar().showMessage(
            f"診療行為マスタ読込完了: {len(self._shinryo_master):,} コード"
        )

    def _on_load_chouzai_master(self) -> None:
        """
        [マスタ] → [調剤行為マスタ] の読込処理。
        """
        paths, _ = QFileDialog.getOpenFileNames(
            self,
            "調剤行為マスタファイルを選択（M マスタをまとめて選択可）",
            "",
            "テキストファイル (*.txt *.csv);;すべてのファイル (*.*)",
        )
        if not paths:
            return

        try:
            path_objs = [Path(p) for p in paths]
            master = load_chouzai_master(path_objs)
        except Exception as e:
            QMessageBox.warning(
                self,
                "調剤行為マスタ読み込みエラー",
                f"調剤行為マスタファイルの読み込みに失敗しました。\n\nエラー: {e}",
            )
            return

        self._chouzai_master = master
        save_master_paths("chouzai", path_objs)
        self._update_master_status("chouzai")

        QMessageBox.information(
            self,
            "調剤行為マスタ読込",
            f"調剤行為マスタを読み込みました。\n"
            f"ファイル数: {len(paths)}\n"
            f"調剤行為コード数: {len(self._chouzai_master):,}",
        )
        self.statusBar().showMessage(
            f"調剤行為マスタ読込完了: {len(self._chouzai_master):,} コード"
        )

    def _on_load_drug_master(self) -> None:
        """
        [マスタ] → [医薬品マスタ] の読込処理。
        """
        paths, _ = QFileDialog.getOpenFileNames(
            self,
            "医薬品マスタファイルを選択（Y マスタをまとめて選択可）",
            "",
            "テキストファイル (*.txt *.csv);;すべてのファイル (*.*)",
        )
        if not paths:
            return

        try:
            path_objs = [Path(p) for p in paths]
            master = load_drug_master(path_objs)
        except Exception as e:
            QMessageBox.warning(
                self,
                "医薬品マスタ読み込みエラー",
                f"医薬品マスタファイルの読み込みに失敗しました。\n\nエラー: {e}",
            )
            return

        self._drug_master = master
        save_master_paths("drug", path_objs)
        self._update_master_status("drug")

        QMessageBox.information(
            self,
            "医薬品マスタ読込",
            f"医薬品マスタを読み込みました。\n"
            f"ファイル数: {len(paths)}\n"
            f"医薬品コード数: {len(self._drug_master):,}",
        )
        self.statusBar().showMessage(
            f"医薬品マスタ読込完了: {len(self._drug_master):,} コード"
        )

    def _on_load_material_master(self) -> None:
        """
        [マスタ] → [特定器材マスタ] の読込処理。
        """
        paths, _ = QFileDialog.getOpenFileNames(
            self,
            "特定器材マスタファイルを選択（T マスタをまとめて選択可）",
            "",
            "テキストファイル (*.txt *.csv);;すべてのファイル (*.*)",
        )
        if not paths:
            return

        try:
            path_objs = [Path(p) for p in paths]
            master = load_material_master(path_objs)
        except Exception as e:
            QMessageBox.warning(
                self,
                "特定器材マスタ読み込みエラー",
                f"特定器材マスタファイルの読み込みに失敗しました。\n\nエラー: {e}",
            )
            return

        self._material_master = master
        save_master_paths("material", path_objs)
        self._update_master_status("material")

        QMessageBox.information(
            self,
            "特定器材マスタ読込",
            f"特定器材マスタを読み込みました。\n"
            f"ファイル数: {len(paths)}\n"
            f"特定器材コード数: {len(self._material_master):,}",
        )
        self.statusBar().showMessage(
            f"特定器材マスタ読込完了: {len(self._material_master):,} コード"
        )

    def _on_load_ward_master(self) -> None:
        """
        [マスタ] → [病棟コードマスタ] の読込処理。
        """
        paths, _ = QFileDialog.getOpenFileNames(
            self,
            "病棟コードマスタファイルを選択（病棟マスタをまとめて選択可）",
            "",
            "テキストファイル (*.txt *.csv);;すべてのファイル (*.*)",
        )
        if not paths:
            return

        try:
            path_objs = [Path(p) for p in paths]
            master = load_ward_master(path_objs)
        except Exception as e:
            QMessageBox.warning(
                self,
                "病棟コードマスタ読み込みエラー",
                f"病棟コードマスタファイルの読み込みに失敗しました。\n\nエラー: {e}",
            )
            return

        self._ward_master = master
        save_master_paths("ward", path_objs)
        self._update_master_status("ward")

        QMessageBox.information(
            self,
            "病棟コードマスタ読込",
            f"病棟コードマスタを読み込みました。\n"
            f"ファイル数: {len(paths)}\n"
            f"病棟コード数: {len(self._ward_master):,}",
        )
        self.statusBar().showMessage(
            f"病棟コードマスタ読込完了: {len(self._ward_master):,} コード"
        )
        
    def _on_load_comment_master(self) -> None:
        """
        [マスタ] → [コメントマスタ] の読込処理。
        """
        paths, _ = QFileDialog.getOpenFileNames(
            self,
            "コメントマスタファイルを選択（C マスタをまとめて選択可）",
            "",
            "テキストファイル (*.txt *.csv);;すべてのファイル (*.*)",
        )
        if not paths:
            return

        try:
            path_objs = [Path(p) for p in paths]
            master = load_comment_master(path_objs)
        except Exception as e:
            QMessageBox.warning(
                self,
                "コメントマスタ読み込みエラー",
                f"コメントマスタファイルの読み込みに失敗しました。\n\nエラー: {e}",
            )
            return

        self._comment_master = master
        save_master_paths("comment", path_objs)
        self._update_master_status("comment")

        QMessageBox.information(
            self,
            "コメントマスタ読込",
            f"コメントマスタを読み込みました。\n"
            f"ファイル数: {len(paths)}\n"
            f"コメントコード数: {len(self._comment_master):,}",
        )
        self.statusBar().showMessage(
            f"コメントマスタ読込完了: {len(self._comment_master):,} コード"
        )

    def _get_disease_name(self, code: str) -> str:
        """
        傷病名コードから漢字名称を取得するヘルパー。
        マスタに存在しない場合は空文字を返す。
        """
        if not code:
            return ""
        info = self._disease_master.get(code.strip())
        if not info:
            return ""
        # 将来的に「漢字/カナ切替」したくなったらここで分岐させる
        return info.get("name") or ""

    def _get_disease_kana(self, code: str) -> str:
        """
        傷病名コード → カナ傷病名（あれば）
        """
        if not code:
            return ""
        info = self._disease_master.get(code.strip())
        if not info:
            return ""
        return info.get("kana") or ""

    def get_modifier_name(self, code: str) -> str:
        if not code:
            return ""
        return self._modifier_name_by_code.get(code, "")

    def get_modifier_kana(self, code: str) -> str:
        if not code:
            return ""
        return self._modifier_kana_by_code.get(code, "")

    def get_shinryo_name(self, code: str) -> str:
        """診療行為コード → 診療行為名称（なければ空文字）。"""
        if not code:
            return ""
        info = self._shinryo_master.get(code.strip())
        if not info:
            return ""
        # マスタ側のキー名は実装に合わせて name / text などを想定
        return info.get("name") or info.get("text") or ""

    def get_drug_name(self, code: str) -> str:
        """医薬品コード → 医薬品名称（なければ空文字）。"""
        if not code:
            return ""
        info = self._drug_master.get(code.strip())
        if not info:
            return ""
        return info.get("name") or info.get("text") or ""

    def get_material_name(self, code: str) -> str:
        """特定器材コード → 器材名称（なければ空文字）。"""
        if not code:
            return ""
        info = self._material_master.get(code.strip())
        if not info:
            return ""
        return info.get("name") or info.get("text") or ""

    def get_iyakuhin_name(self, code: str) -> str:
        """
        IYレコード向け: 医薬品コード → 医薬品名称。
        実体は get_drug_name() をそのまま利用する。
        """
        return self.get_drug_name(code)

    def get_tokutei_kizai_name(self, code: str) -> str:
        """
        TOレコード向け: 特定器材コード → 器材名称。
        実体は get_material_name() をそのまま利用する。
        """
        return self.get_material_name(code)

    def get_comment_text(self, code: str) -> str:
        """コメントコード → コメント文字列（なければ空文字）。
        現状は将来のコメントマスタ読込に備えたフックとして利用します。
        """
        if not code:
            return ""
        info = self._comment_master.get(code.strip())
        if not info:
            return ""
        return info.get("text") or info.get("name") or ""

    def _is_abolished(self, info: dict[str, str] | None) -> bool:
        """マスタ1件分の dict から『廃止コード』かどうかをゆるく判定するヘルパー。

        - end_ymd が空、または 00000000 / 99999999 の場合は現役扱い
        - それ以外であれば『廃止済み』として True を返す
        （診療年月までは考慮しない『軽い利用』）
        """
        if not info:
            return False

        end_ymd = (info.get("end_ymd") or "").strip()
        if not end_ymd:
            return False

        # 代表的なダミー値は『未廃止』扱い
        if end_ymd in {"00000000", "99999999"}:
            return False

        # ここでは日付の詳細な妥当性チェックは行わず、
        # 『何らかの終了年月日が入っている』ものを廃止扱いとする
        return True

    def is_disease_abolished(self, code: str) -> bool:
        """傷病名コードがマスタ上『廃止』かどうかを簡易判定する。"""
        if not code:
            return False
        info = self._disease_master.get(code.strip())
        return self._is_abolished(info)

    def is_shinryo_abolished(self, code: str) -> bool:
        """診療行為コードがマスタ上『廃止』かどうかを簡易判定する。"""
        if not code:
            return False
        info = self._shinryo_master.get(code.strip())
        return self._is_abolished(info)

    # ─────────────────────────────
    # 検索ロジック
    # ─────────────────────────────
    def _jump_to_receipt(self, index: int, source: str = "検索") -> None:
        """
        レセプト一覧タブで指定インデックスのレセプトを選択・表示する共通ヘルパー。
        """
        if index < 0 or index >= len(self._receipts):
            return

        self.tabs.setCurrentIndex(self.TAB_RECEIPTS)
        self.receipt_list.setCurrentRow(index)
        self.receipt_list.scrollToItem(self.receipt_list.currentItem())

        receipt = self._receipts[index]
        h = receipt.header
        if h:
            msg = (
                f"{source}: レセプト {receipt.index} "
                f"(患者番号={h.patient_id or '-'}, 診療年月={h.year_month or '-'}) を表示中"
            )
        else:
            msg = f"{source}: レセプト {receipt.index} を表示中"

        self.statusBar().showMessage(msg)

    def _on_global_search(self) -> None:
        """
        表示 → 詳細検索 (Ctrl+Alt+F)
        専用の検索ウインドウ（GlobalSearchDialog）を開き、
        名前・患者番号・レセプト番号・病名・医薬品・診療行為など
        複数条件での検索を行う。
        """
        if not self._receipts:
            QMessageBox.information(self, "詳細検索", "レセプトが読み込まれていません。")
            return

        # GlobalSearchDialog 側で結果一覧を表示し、
        # ダブルクリックなどで _jump_to_receipt を呼び出す前提のインターフェースにしておく
        if self._global_search_dialog is None:
            dlg = GlobalSearchDialog(
                parent=self,
                receipts=self._receipts,
                on_jump_to_receipt=self._jump_to_receipt,
                get_disease_name=self._get_disease_name,
                get_modifier_name=self.get_modifier_name,
                get_shinryo_name=self.get_shinryo_name,
                get_drug_name=self.get_drug_name,
                get_material_name=self.get_material_name,
                get_comment_text=self.get_comment_text,
            )
            dlg.finished.connect(
                lambda _result: setattr(self, "_global_search_dialog", None)
            )
            self._global_search_dialog = dlg
        
        dlg = self._global_search_dialog
        
        dlg.show()
        dlg.raise_()
        dlg.activateWindow()

    def _on_header_search(self) -> None:
        """
        表示 → ヘッダ検索 (Ctrl+H)
        レセプトヘッダ情報（患者番号・氏名・診療年月など）を対象に検索する。
        HeaderSearchDialog で条件を入力し、search_receipts_by_header() でヒットした
        レセプトにジャンプする。
        """
        if not self._receipts:
            QMessageBox.information(self, "ヘッダ検索", "レセプトが読み込まれていません。")
            return

        # ヘッダ検索ダイアログを表示
        dlg = HeaderSearchDialog(self)

        # exec() は Accept/Reject を int で返す（1=Accepted, 0=Rejected）
        result = dlg.exec()
        if result != 1:
            # キャンセル時などは何もしない
            return

        # 条件の取得（実装に合わせて get_conditions() 優先、なければ .conditions を見る）
        conditions: dict = {}
        if hasattr(dlg, "get_conditions"):
            try:
                conditions = dlg.get_conditions()  # type: ignore[assignment]
            except Exception:
                conditions = {}
        elif hasattr(dlg, "conditions"):
            try:
                conditions = getattr(dlg, "conditions") or {}
            except Exception:
                conditions = {}

        # 条件が空でも search_receipts_by_header 側で適切に解釈する前提
        hits = search_receipts_by_header(self._receipts, conditions)

        # 結果を保持して「レセプト次を検索」と連携
        self._receipt_search_hits = hits
        self._receipt_search_index = -1

        if not hits:
            QMessageBox.information(self, "ヘッダ検索", "条件に一致するレセプトは見つかりませんでした。")
            self.statusBar().showMessage("ヘッダ検索: ヒット 0 件")
            return

        # 最初のヒットに移動
        self._receipt_search_index = 0
        first_idx = self._receipt_search_hits[self._receipt_search_index]

        self.tabs.setCurrentIndex(self.TAB_RECEIPTS)  # レセプト一覧タブへ
        self.receipt_list.setCurrentRow(first_idx)
        self.receipt_list.scrollToItem(self.receipt_list.currentItem())

        self.statusBar().showMessage(
            f"ヘッダ検索: {len(hits)} 件ヒット / 1 件目を表示"
        )

    def _on_search(self) -> None:
        """
        表示 → 検索 (Ctrl+F)
        レコード一覧（全レコード）の raw テキストに対して部分一致検索する。
        """
        if not self._records:
            QMessageBox.information(self, "検索", "レコードが読み込まれていません。")
            return

        text, ok = QInputDialog.getText(self, "検索", "検索文字列を入力してください：")
        if not ok or not text:
            return

        keyword = str(text)

        hits: list[int] = []
        for idx, rec in enumerate(self._records):
            if keyword in rec.raw:
                hits.append(idx)

        self._search_hits = hits
        self._search_index = -1

        if not hits:
            QMessageBox.information(self, "検索", f"「{keyword}」は見つかりませんでした。")
            self.statusBar().showMessage(f"検索「{keyword}」: ヒット 0 件")
            return

        # 最初のヒットに移動
        self._search_index = 0
        first_idx = self._search_hits[self._search_index]
        self.tabs.setCurrentIndex(self.TAB_RECORDS)  # レコード一覧タブへ切り替え
        self.record_list.setCurrentRow(first_idx)
        self.record_list.scrollToItem(self.record_list.currentItem())

        self.statusBar().showMessage(
            f"検索「{keyword}」: {len(hits)} 件ヒット / 1 件目を表示"
        )

    def _on_search_next(self) -> None:
        """
        表示 → 次を検索 (F3 相当)
        """
        if not self._records:
            return

        if not self._search_hits:
            # まだ検索していない場合は通常の検索ダイアログを出す
            self._on_search()
            return

        if self._search_index < 0:
            self._search_index = 0
        else:
            self._search_index += 1

        if self._search_index >= len(self._search_hits):
            # 末尾まで行ったら先頭に戻る
            self._search_index = 0

        idx = self._search_hits[self._search_index]
        self.tabs.setCurrentIndex(self.TAB_RECORDS)  # レコード一覧タブへ
        self.record_list.setCurrentRow(idx)
        self.record_list.scrollToItem(self.record_list.currentItem())

        self.statusBar().showMessage(
            f"検索結果: {len(self._search_hits)} 件中 "
            f"{self._search_index + 1} 件目を表示"
        )

    def _on_receipt_search(self) -> None:
        """
        表示 → レセプト検索 (Ctrl+Shift+F)
        各レセプト内の全レコード raw テキストを連結したものに対して部分一致検索する。
        """
        if not self._receipts:
            QMessageBox.information(self, "レセプト検索", "レセプトが読み込まれていません。")
            return

        text, ok = QInputDialog.getText(self, "レセプト検索", "検索文字列を入力してください：")
        if not ok or not text:
            return

        keyword = str(text)

        hits: list[int] = []
        for idx, receipt in enumerate(self._receipts):
            # レセプト内のすべての raw を結合して検索対象にする
            joined = "\n".join(rec.raw for rec in receipt.records)
            if keyword in joined:
                hits.append(idx)

        self._receipt_search_hits = hits
        self._receipt_search_index = -1

        if not hits:
            QMessageBox.information(self, "レセプト検索", f"「{keyword}」は見つかりませんでした。")
            self.statusBar().showMessage(f"レセプト検索「{keyword}」: ヒット 0 件")
            return

        # 最初のヒットに移動
        self._receipt_search_index = 0
        first_idx = self._receipt_search_hits[self._receipt_search_index]

        self.tabs.setCurrentIndex(self.TAB_RECEIPTS)  # レセプト一覧タブへ
        self.receipt_list.setCurrentRow(first_idx)
        self.receipt_list.scrollToItem(self.receipt_list.currentItem())

        self.statusBar().showMessage(
            f"レセプト検索「{keyword}」: {len(hits)} 件ヒット / 1 件目を表示"
        )

    def _on_receipt_search_next(self) -> None:
        """
        表示 → レセプト次を検索 (Ctrl+Shift+N)
        """
        if not self._receipts:
            return

        if not self._receipt_search_hits:
            # まだ検索していない場合は通常のレセプト検索を起動
            self._on_receipt_search()
            return

        if self._receipt_search_index < 0:
            self._receipt_search_index = 0
        else:
            self._receipt_search_index += 1

        if self._receipt_search_index >= len(self._receipt_search_hits):
            # 末尾まで行ったら先頭に戻る
            self._receipt_search_index = 0

        idx = self._receipt_search_hits[self._receipt_search_index]

        self.tabs.setCurrentIndex(self.TAB_RECEIPTS)  # レセプト一覧タブへ
        self.receipt_list.setCurrentRow(idx)
        self.receipt_list.scrollToItem(self.receipt_list.currentItem())

        self.statusBar().showMessage(
            f"レセプト検索結果: {len(self._receipt_search_hits)} 件中 "
            f"{self._receipt_search_index + 1} 件目を表示"
        )

    # ─────────────────────────────
    # 種別点数情報用ヘルパー
    # ─────────────────────────────
    def _normalize_digits(self, s: str) -> str:
        """
        全角数字が混じっていても扱えるように、数字だけ半角に揃える。
        """
        if not s:
            return ""
        table = str.maketrans({
            "０": "0", "１": "1", "２": "2", "３": "3", "４": "4",
            "５": "5", "６": "6", "７": "7", "８": "8", "９": "9",
        })
        return s.translate(table)

    def _extract_pref_from_insurer(self, insurer: str) -> str:
        """
        保険者番号から都道府県コード(2桁)を推定する。

        - 8桁 … 3〜4桁目
        - 6桁 … 先頭2桁
        - それ以外 … 不明扱い（空文字）
        """
        s = self._normalize_digits(insurer or "")
        # 数字以外は削る（念のため）
        s = "".join(ch for ch in s if ch.isdigit())
        if len(s) >= 8:
            return s[2:4]          # 3〜4桁目（0-based index）
        elif len(s) >= 6:
            return s[0:2]          # 先頭2桁
        else:
            return ""

    def _points_group_key(self, insurer: str) -> tuple[str, str]:
        """
        種別点数情報の集計モードに応じて、
        ・グループID（内部キー）
        ・保険者列に表示するラベル
        を返す。

        ルール:
        - 保険者番号が8桁で、先頭2桁が「39」のときだけ
            → 「後期高齢者医療広域連合」として県単位でまとめる候補
              （都道府県番号は3〜4桁目）
        - それ以外（6桁国保や法別≠39）はすべて保険者番号ごと
        """
        insurer = insurer or "-"
        mode = self.points_group_mode
        facility_pref = (self._facility_pref_code or "").zfill(2)

        # 数字だけを取り出して 8 桁 & 先頭 "39" かを確認
        digits = "".join(ch for ch in self._normalize_digits(insurer) if ch.isdigit())

        is_kouki_wide = False
        kouki_pref = ""

        if len(digits) == 8 and digits[:2] == "39":
            # 3〜4桁目が都道府県番号
            kouki_pref = digits[2:4].zfill(2)
            is_kouki_wide = True

        # 県単位で広域連合をまとめる
        if mode == self.GROUP_ALL_WIDE_BY_PREF and is_kouki_wide:
            pref_name = PREF_NAMES.get(kouki_pref, f"{kouki_pref}県")
            label = f"{pref_name}後期高齢者医療広域連合"
            group_id = f"pref:{kouki_pref}"
            return group_id, label

        # 自県の広域連合だけまとめる
        if mode == self.GROUP_OWN_PREF_ONLY and is_kouki_wide:
            if kouki_pref == facility_pref:
                pref_name = PREF_NAMES.get(kouki_pref, f"{kouki_pref}県")
                label = f"{pref_name}後期高齢者医療広域連合"
                group_id = f"pref:{kouki_pref}"
                return group_id, label
            # 他県の広域連合は保険者単位のまま

        # デフォルト: 保険者番号ごと
        return insurer, insurer

    # ─────────────────────────────
    # 共通ヘルパー関数
    # ─────────────────────────────
    def _format_claim_ym_jp(self, yyyymm: str) -> str:
        """
        202509 -> R07.09 のように簡易和暦表記に変換する。
        （Reiwa/Heisei だけざっくり対応）
        """
        if len(yyyymm) != 6 or not yyyymm.isdigit():
            return yyyymm

        year = int(yyyymm[:4])
        month = int(yyyymm[4:6])

        # 2019年以降は令和として扱う（R01=2019）
        if year >= 2019:
            era_year = year - 2018
            return f"R{era_year:02d}.{month:02d}"
        # 1989〜2018 を簡易に平成として扱う（H01=1989）
        elif year >= 1989:
            era_year = year - 1988
            return f"H{era_year:02d}.{month:02d}"
        else:
            # それ以前は素直に西暦で返す
            return f"{year}.{month:02d}"

