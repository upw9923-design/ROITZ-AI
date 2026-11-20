"""
HistoryPanel — Conversation History UI for ROITZ AI.

Provides a split-view panel for browsing conversation history:
- Left: Conversation list with pagination
- Right: Message detail view with pagination
- Search input (UI only, no backend yet)
- Loading, empty, and error states
- Independent dismiss control

Keyboard Navigation:
- Tab / Shift+Tab: Move focus through controls in logical order
- Up/Down arrows: Navigate conversation list items
- Enter/Return: Open selected conversation
- Escape: Clear search input (if focused) or dismiss panel
- Left/Right arrows: Navigate list pagination (when list focused)
- Ctrl+Left/Ctrl+Right: Navigate detail pagination (when detail focused)
- Page Up/Page Down: Jump by 5 pages in list/detail pagination
"""
from __future__ import annotations

from PyQt6.QtCore import Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QFont, QKeyEvent, QFocusEvent
from PyQt6.QtGui import QStandardItemModel, QStandardItem
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QListView, QTextEdit, QLineEdit, QFrame, QSplitter,
    QSizePolicy, QAbstractItemView
)

from ui import C  # Use the shared color palette


class HistoryPanel(QWidget):
    """
    Standalone history panel widget.

    Does not perform any database operations. All data loading is expected
    to be driven by external signals (list, detail, search, error).
    """

    # Emitted when user selects a conversation in the list
    conversation_selected = pyqtSignal(str)  # conversation_id

    # Emitted when user clicks list pagination controls
    list_page_requested = pyqtSignal(int)  # page number (0-based)

    # Emitted when user clicks detail pagination controls
    detail_page_requested = pyqtSignal(int)  # page number (0-based)

    # Emitted when search text changes (debounced)
    search_requested = pyqtSignal(str)  # query string

    # Emitted when user dismisses the panel (via button or Escape)
    dismissed = pyqtSignal()

    # Emitted when user clicks "Resume Session" button with conversation_id
    session_resumed = pyqtSignal(str)  # conversation_id

    def __init__(self, parent: QWidget | None = None, assistant_name: str = "JARVIS"):
        super().__init__(parent)
        self.setObjectName("HistoryPanel")
        self.setStyleSheet(f"""
            QWidget#HistoryPanel {{
                background: {C.PANEL};
                border-top: 1px solid {C.BORDER_B};
            }}
        """)
        # Minimum height prevents collapsing to 0px via splitter drag
        self.setMinimumHeight(200)
        self.hide()

        # Pagination state
        self._current_list_page = 0
        self._total_list_pages = 1
        self._current_detail_page = 0
        self._total_detail_pages = 1
        self._selected_conversation_id: str | None = None
        self._assistant_name = assistant_name.upper()

        # Search state
        self._current_search_query: str = ""

        # Search debounce timer
        self._search_timer = QTimer(self)
        self._search_timer.setSingleShot(True)
        self._search_timer.setInterval(300)
        self._search_timer.timeout.connect(self._emit_search)

        self._build_ui()

    def _build_ui(self) -> None:
        lay = QVBoxLayout(self)
        lay.setContentsMargins(12, 7, 12, 8)
        lay.setSpacing(5)

        # Header row
        hdr = QHBoxLayout()
        hdr.setSpacing(6)

        dot = QLabel("◈")
        dot.setFont(QFont("Courier New", 9, QFont.Weight.Bold))
        dot.setStyleSheet(f"color: {C.PRI}; background: transparent;")
        hdr.addWidget(dot)

        self._title_lbl = QLabel("HISTORY")
        self._title_lbl.setFont(QFont("Courier New", 8, QFont.Weight.Bold))
        self._title_lbl.setStyleSheet(
            f"color: {C.PRI}; background: transparent; letter-spacing: 1px;"
        )
        hdr.addWidget(self._title_lbl)

        hdr.addStretch()

        self._page_lbl = QLabel("Page 1 / 1")
        self._page_lbl.setFont(QFont("Courier New", 7))
        self._page_lbl.setStyleSheet(f"color: {C.TEXT_DIM}; background: transparent;")
        hdr.addWidget(self._page_lbl)

        self._dismiss_btn = QPushButton("DISMISS  ✕")
        self._dismiss_btn.setFont(QFont("Courier New", 7))
        self._dismiss_btn.setFixedHeight(18)
        self._dismiss_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._dismiss_btn.setAccessibleName("Dismiss history panel")
        self._dismiss_btn.setAccessibleDescription("Closes the history panel")
        self._dismiss_btn.setStyleSheet(f"""
            QPushButton {{
                background: transparent; color: {C.TEXT_DIM};
                border: 1px solid {C.BORDER}; border-radius: 2px; padding: 0 5px;
            }}
            QPushButton:hover {{ color: {C.TEXT}; border-color: {C.BORDER_B}; }}
            QPushButton:focus {{ border-color: {C.PRI}; outline: 1px solid {C.PRI}; }}
        """)
        self._dismiss_btn.clicked.connect(self._on_dismiss)
        hdr.addWidget(self._dismiss_btn)

        lay.addLayout(hdr)

        # Search input with clear button
        search_row = QHBoxLayout()
        search_row.setSpacing(4)
        search_row.setContentsMargins(0, 0, 0, 0)

        self._search_input = QLineEdit()
        self._search_input.setPlaceholderText("Search conversations…")
        self._search_input.setFont(QFont("Courier New", 8))
        self._search_input.setAccessibleName("Search conversations")
        self._search_input.setAccessibleDescription("Type to search conversation history by title, summary, or message content")
        self._search_input.setStyleSheet(f"""
            QLineEdit {{
                background: {C.DARK};
                color: {C.TEXT};
                border: 1px solid {C.BORDER};
                border-radius: 3px;
                padding: 4px 8px;
                padding-right: 28px;
                selection-background-color: {C.PRI_GHO};
            }}
            QLineEdit:focus {{ border-color: {C.PRI}; outline: 1px solid {C.PRI}; }}
        """)
        self._search_input.textChanged.connect(self._on_search_text_changed)
        self._search_input.installEventFilter(self)
        search_row.addWidget(self._search_input)

        # Clear search button (shows when search has text)
        self._search_clear_btn = QPushButton("✕")
        self._search_clear_btn.setFont(QFont("Courier New", 8))
        self._search_clear_btn.setFixedSize(20, 20)
        self._search_clear_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._search_clear_btn.setAccessibleName("Clear search")
        self._search_clear_btn.setAccessibleDescription("Clear the search query")
        self._search_clear_btn.setStyleSheet(f"""
            QPushButton {{
                background: transparent; color: {C.TEXT_DIM};
                border: none; border-radius: 2px;
            }}
            QPushButton:hover {{ color: {C.TEXT}; background: {C.BORDER_A}; }}
            QPushButton:focus {{ border-color: {C.PRI}; outline: 1px solid {C.PRI}; }}
        """)
        self._search_clear_btn.clicked.connect(self._clear_search)
        self._search_clear_btn.hide()
        search_row.addWidget(self._search_clear_btn)

        lay.addLayout(search_row)

        # Separator
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet(f"color: {C.BORDER};")
        lay.addWidget(sep)

        # Split view: List (left) | Detail (right)
        self._split = QSplitter(Qt.Orientation.Horizontal)
        self._split.setStyleSheet(f"""
            QSplitter::handle {{
                background: {C.BORDER};
                width: 4px;
            }}
            QSplitter::handle:hover {{
                background: {C.PRI_DIM};
            }}
        """)
        self._split.setChildrenCollapsible(False)

        # Left: Conversation list
        self._list_widget = self._build_list_view()
        self._split.addWidget(self._list_widget)

        # Right: Message detail
        self._detail_widget = self._build_detail_view()
        self._split.addWidget(self._detail_widget)

        # Initial split: 40% list, 60% detail
        self._split.setSizes([280, 420])

        lay.addWidget(self._split, stretch=1)

        # List pagination controls
        list_pager = self._build_pager("list")
        lay.addLayout(list_pager)

        # Detail pagination controls
        detail_pager = self._build_pager("detail")
        lay.addLayout(detail_pager)

        # Set explicit tab order for logical keyboard navigation
        self._setup_tab_order()

    def _build_list_view(self) -> QWidget:
        """Build the conversation list view."""
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(4)

        self._list_model = QStandardItemModel()
        self._list_model.setHorizontalHeaderLabels(["Conversation"])

        self._list_view = QListView()
        self._list_view.setModel(self._list_model)
        self._list_view.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self._list_view.setUniformItemSizes(True)
        self._list_view.setFont(QFont("Courier New", 8))
        self._list_view.setAccessibleName("Conversation list")
        self._list_view.setAccessibleDescription("List of conversations. Use Up/Down arrows to navigate, Enter to open, Left/Right arrows to change pages")
        self._list_view.setStyleSheet(f"""
            QListView {{
                background: {C.DARK};
                color: {C.TEXT};
                border: 1px solid {C.BORDER};
                border-radius: 3px;
            }}
            QListView::item {{
                padding: 6px 8px;
                border-bottom: 1px solid {C.BORDER_A};
            }}
            QListView::item:selected {{
                background: {C.PRI_GHO};
                color: {C.PRI};
            }}
            QListView::item:selected:focus {{
                background: {C.PRI_GHO};
                color: {C.PRI};
                outline: 1px solid {C.PRI};
            }}
            QListView::item:hover {{
                background: {C.BORDER_A};
            }}
            QListView:focus {{
                border-color: {C.PRI};
                outline: 1px solid {C.PRI};
            }}
            QScrollBar:vertical {{
                background: {C.BG}; width: 6px; border: none;
            }}
            QScrollBar::handle:vertical {{
                background: {C.BORDER_B}; border-radius: 3px; min-height: 16px;
            }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
                height: 0; border: none;
            }}
        """)
        self._list_view.clicked.connect(self._on_list_clicked)
        self._list_view.installEventFilter(self)
        lay.addWidget(self._list_view)

        # Empty state label (shown when model is empty)
        self._list_empty_lbl = QLabel("No conversations yet.")
        self._list_empty_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._list_empty_lbl.setFont(QFont("Courier New", 9))
        self._list_empty_lbl.setStyleSheet(f"color: {C.TEXT_DIM}; background: transparent;")
        self._list_empty_lbl.setAccessibleName("Empty conversation list")
        self._list_empty_lbl.hide()
        lay.addWidget(self._list_empty_lbl)

        # Loading state label
        self._list_loading_lbl = QLabel("Loading conversations…")
        self._list_loading_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._list_loading_lbl.setFont(QFont("Courier New", 9))
        self._list_loading_lbl.setStyleSheet(f"color: {C.PRI}; background: transparent;")
        self._list_loading_lbl.setAccessibleName("Loading conversations")
        self._list_loading_lbl.hide()
        lay.addWidget(self._list_loading_lbl)

        return w

    def _build_detail_view(self) -> QWidget:
        """Build the message detail view."""
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(4)

        # Detail header with conversation title and resume button
        header_lay = QHBoxLayout()
        header_lay.setContentsMargins(0, 0, 0, 0)
        header_lay.setSpacing(8)

        self._detail_title_lbl = QLabel("Select a conversation")
        self._detail_title_lbl.setFont(QFont("Courier New", 8, QFont.Weight.Bold))
        self._detail_title_lbl.setStyleSheet(f"color: {C.TEXT_MED}; background: transparent;")
        self._detail_title_lbl.setAccessibleName("Conversation title")
        header_lay.addWidget(self._detail_title_lbl)

        # Resume Session button (hidden until conversation is selected)
        self._resume_btn = QPushButton("RESUME SESSION")
        self._resume_btn.setFont(QFont("Courier New", 7))
        self._resume_btn.setMaximumWidth(120)
        self._resume_btn.setStyleSheet(f"""
            QPushButton {{
                background: {C.PRI_GHO}; color: {C.PRI}; border: 1px solid {C.PRI_DIM};
                border-radius: 2px; padding: 4px 8px;
            }}
            QPushButton:hover {{ background: {C.PRI}; color: {C.DARK}; }}
            QPushButton:pressed {{ background: {C.PRI_DIM}; }}
            QPushButton:disabled {{ color: {C.TEXT_DIM}; border-color: {C.BORDER}; background: {C.BORDER_A}; }}
            QPushButton:focus {{ outline: 1px solid {C.PRI}; }}
        """)
        self._resume_btn.setAccessibleName("Resume session")
        self._resume_btn.setAccessibleDescription("Resume this conversation in a new session")
        self._resume_btn.hide()
        self._resume_btn.clicked.connect(self._on_resume_clicked)
        header_lay.addStretch()
        header_lay.addWidget(self._resume_btn)

        lay.addLayout(header_lay)

        self._detail_display = QTextEdit()
        self._detail_display.setReadOnly(True)
        self._detail_display.setFont(QFont("Courier New", 8))
        self._detail_display.setAccessibleName("Message history")
        self._detail_display.setAccessibleDescription("Conversation messages. Use Ctrl+Left/Right arrows or Page Up/Down to navigate pages")
        self._detail_display.setStyleSheet(f"""
            QTextEdit {{
                background: {C.DARK};
                color: {C.TEXT};
                border: 1px solid {C.BORDER};
                border-radius: 3px;
                padding: 6px 8px;
                selection-background-color: {C.PRI_GHO};
            }}
            QTextEdit:focus {{
                border-color: {C.PRI};
                outline: 1px solid {C.PRI};
            }}
            QScrollBar:vertical {{
                background: {C.BG}; width: 6px; border: none;
            }}
            QScrollBar::handle:vertical {{
                background: {C.BORDER_B}; border-radius: 3px; min-height: 16px;
            }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
                height: 0; border: none;
            }}
        """)
        self._detail_display.installEventFilter(self)
        lay.addWidget(self._detail_display, stretch=1)

        # Empty state for detail
        self._detail_empty_lbl = QLabel("Select a conversation to view messages.")
        self._detail_empty_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._detail_empty_lbl.setFont(QFont("Courier New", 9))
        self._detail_empty_lbl.setStyleSheet(f"color: {C.TEXT_DIM}; background: transparent;")
        self._detail_empty_lbl.setAccessibleName("Empty message detail")
        self._detail_empty_lbl.hide()
        lay.addWidget(self._detail_empty_lbl)

        # Loading state for detail
        self._detail_loading_lbl = QLabel("Loading messages…")
        self._detail_loading_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._detail_loading_lbl.setFont(QFont("Courier New", 9))
        self._detail_loading_lbl.setStyleSheet(f"color: {C.PRI}; background: transparent;")
        self._detail_loading_lbl.setAccessibleName("Loading messages")
        self._detail_loading_lbl.hide()
        lay.addWidget(self._detail_loading_lbl)

        # Error state for detail
        self._detail_error_lbl = QLabel("")
        self._detail_error_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._detail_error_lbl.setFont(QFont("Courier New", 9))
        self._detail_error_lbl.setStyleSheet(f"color: {C.RED}; background: transparent;")
        self._detail_error_lbl.setAccessibleName("Error loading messages")
        self._detail_error_lbl.hide()
        lay.addWidget(self._detail_error_lbl)

        return w

    def _build_pager(self, which: str) -> QHBoxLayout:
        """Build a pagination control row (Prev / Page X of Y / Next)."""
        pager = QHBoxLayout()
        pager.setSpacing(6)
        pager.addStretch()

        prev_btn = QPushButton("← Prev")
        prev_btn.setFont(QFont("Courier New", 7))
        prev_btn.setFixedHeight(20)
        prev_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        prev_btn.setStyleSheet(f"""
            QPushButton {{
                background: {C.PANEL2}; color: {C.TEXT};
                border: 1px solid {C.BORDER}; border-radius: 2px; padding: 0 8px;
            }}
            QPushButton:hover {{ border-color: {C.PRI_DIM}; }}
            QPushButton:disabled {{ color: {C.TEXT_DIM}; border-color: {C.BORDER}; }}
            QPushButton:focus {{ border-color: {C.PRI}; outline: 1px solid {C.PRI}; }}
        """)

        page_lbl = QLabel("Page 1 / 1")
        page_lbl.setFont(QFont("Courier New", 7))
        page_lbl.setStyleSheet(f"color: {C.TEXT_DIM}; background: transparent;")

        next_btn = QPushButton("Next →")
        next_btn.setFont(QFont("Courier New", 7))
        next_btn.setFixedHeight(20)
        next_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        next_btn.setStyleSheet(f"""
            QPushButton {{
                background: {C.PANEL2}; color: {C.TEXT};
                border: 1px solid {C.BORDER}; border-radius: 2px; padding: 0 8px;
            }}
            QPushButton:hover {{ border-color: {C.PRI_DIM}; }}
            QPushButton:disabled {{ color: {C.TEXT_DIM}; border-color: {C.BORDER}; }}
            QPushButton:focus {{ border-color: {C.PRI}; outline: 1px solid {C.PRI}; }}
        """)

        if which == "list":
            self._list_prev_btn = prev_btn
            self._list_page_lbl = page_lbl
            self._list_next_btn = next_btn
            prev_btn.clicked.connect(lambda: self._on_page_change("list", -1))
            next_btn.clicked.connect(lambda: self._on_page_change("list", +1))
            prev_btn.setAccessibleName("Previous page")
            prev_btn.setAccessibleDescription("Go to previous page of conversations (Left arrow)")
            next_btn.setAccessibleName("Next page")
            next_btn.setAccessibleDescription("Go to next page of conversations (Right arrow)")
            page_lbl.setAccessibleName("Conversation list page indicator")
        else:
            self._detail_prev_btn = prev_btn
            self._detail_page_lbl = page_lbl
            self._detail_next_btn = next_btn
            prev_btn.clicked.connect(lambda: self._on_page_change("detail", -1))
            next_btn.clicked.connect(lambda: self._on_page_change("detail", +1))
            prev_btn.setAccessibleName("Previous message page")
            prev_btn.setAccessibleDescription("Go to previous page of messages (Ctrl+Left arrow)")
            next_btn.setAccessibleName("Next message page")
            next_btn.setAccessibleDescription("Go to next page of messages (Ctrl+Right arrow)")
            page_lbl.setAccessibleName("Message detail page indicator")

        pager.addWidget(prev_btn)
        pager.addWidget(page_lbl)
        pager.addWidget(next_btn)
        pager.addStretch()

        return pager

    # Public API for external data loading

    def set_conversation_list(
        self,
        conversations: list[dict],
        page: int,
        total_pages: int,
        total_count: int,
    ) -> None:
        """
        Populate the conversation list.

        Args:
            conversations: List of conversation dicts with keys:
                id, title, started_at, ended_at, turn_count, summary, engine
            page: Current page (0-based)
            total_pages: Total number of pages
            total_count: Total conversations across all pages
        """
        self._current_list_page = page
        self._total_list_pages = max(1, total_pages)
        self._list_page_lbl.setText(f"Page {page + 1} / {self._total_list_pages} (Total: {total_count})")
        self._list_prev_btn.setEnabled(page > 0)
        self._list_next_btn.setEnabled(page < self._total_list_pages - 1)

        self._list_model.removeRows(0, self._list_model.rowCount())

        if not conversations:
            self._list_view.hide()
            self._list_loading_lbl.hide()
            # Show different empty message for search vs no conversations
            if self._current_search_query:
                self._list_empty_lbl.setText(f"No results for \"{self._current_search_query}\"")
                self._list_empty_lbl.setAccessibleName("No search results")
            else:
                self._list_empty_lbl.setText("No conversations yet.")
                self._list_empty_lbl.setAccessibleName("Empty conversation list")
            self._list_empty_lbl.show()
            return

        self._list_empty_lbl.hide()
        self._list_loading_lbl.hide()
        self._list_view.show()

        for conv in conversations:
            title = conv.get("title") or "Untitled conversation"
            # Fallback for auto-generated timestamp titles
            if title.startswith("Conversation ") and title[13:].isdigit():
                title = "Untitled conversation"

            started = conv.get("started_at", 0)
            ended = conv.get("ended_at")
            turn_count = conv.get("turn_count", 0)
            engine = conv.get("engine", "gemini_live")

            # Format date
            from datetime import datetime
            try:
                dt = datetime.fromtimestamp(started / 1000)
                date_str = dt.strftime("%Y-%m-%d %H:%M")
            except Exception:
                date_str = "Unknown date"

            status = "● Active" if ended is None else "○ Ended"
            status_color = C.GREEN if ended is None else C.TEXT_DIM

            item_text = f"{title}\n{date_str}  •  {turn_count} turns  •  {engine}  •  {status}"
            item = QStandardItem(item_text)
            item.setData(conv.get("id"), Qt.ItemDataRole.UserRole)
            self._list_model.appendRow(item)

    def set_message_detail(
        self,
        conversation_id: str,
        title: str,
        messages: list[dict],
        page: int,
        total_pages: int,
        total_count: int,
    ) -> None:
        """
        Populate the message detail view.

        Args:
            conversation_id: The conversation ID
            title: Conversation title for header
            messages: List of message dicts with keys:
                role, content, content_type, sequence, timestamp_ms
            page: Current page (0-based)
            total_pages: Total number of pages
            total_count: Total messages across all pages
        """
        # Store conversation ID for resume functionality
        self._selected_conversation_id = conversation_id

        self._current_detail_page = page
        self._total_detail_pages = max(1, total_pages)
        self._detail_page_lbl.setText(f"Page {page + 1} / {self._total_detail_pages} (Total: {total_count})")
        self._detail_prev_btn.setEnabled(page > 0)
        self._detail_next_btn.setEnabled(page < self._total_detail_pages - 1)

        # Update header and show resume button
        display_title = title or "Untitled conversation"
        if display_title.startswith("Conversation ") and display_title[13:].isdigit():
            display_title = "Untitled conversation"
        self._detail_title_lbl.setText(display_title)
        self._resume_btn.show()

        if not messages:
            self._detail_display.hide()
            self._detail_empty_lbl.show()
            self._detail_loading_lbl.hide()
            self._detail_error_lbl.hide()
            return

        self._detail_empty_lbl.hide()
        self._detail_loading_lbl.hide()
        self._detail_error_lbl.hide()
        self._detail_display.show()

        # Build HTML for messages
        parts = []
        for msg in messages:
            role = msg.get("role", "unknown")
            content = msg.get("content", "")
            content_type = msg.get("content_type", "text")
            timestamp = msg.get("timestamp_ms", 0)

            from datetime import datetime
            try:
                dt = datetime.fromtimestamp(timestamp / 1000)
                time_str = dt.strftime("%H:%M:%S")
            except Exception:
                time_str = "??:??:??"

            if role == "user":
                role_color = C.PRI
                role_label = "YOU"
            elif role == "assistant":
                role_color = C.GREEN
                role_label = self._assistant_name
            elif role == "system":
                role_color = C.ACC2
                role_label = "SYS"
            else:
                role_color = C.TEXT_DIM
                role_label = role.upper()

            type_badge = ""
            if content_type != "text":
                type_badge = f' <span style="color:{C.TEXT_DIM}; font-size:7px;">[{content_type}]</span>'

            parts.append(
                f'<div style="margin-bottom:8px;">'
                f'<span style="color:{role_color}; font-weight:bold;">{role_label}</span>'
                f'{type_badge}'
                f'<span style="color:{C.TEXT_DIM}; float:right;">{time_str}</span>'
                f'<br><span style="color:{C.TEXT}; white-space:pre-wrap;">{self._esc(content)}</span>'
                f'</div>'
            )

        self._detail_display.setHtml("".join(parts))
        self._detail_display.moveCursor(
            self._detail_display.textCursor().MoveOperation.Start
        )

    def set_detail_loading(self, loading: bool) -> None:
        """Show/hide loading state in detail view."""
        self._detail_loading_lbl.setVisible(loading)
        self._detail_display.setVisible(not loading)
        self._detail_empty_lbl.setVisible(False)
        self._detail_error_lbl.setVisible(False)

    def set_detail_error(self, error: str) -> None:
        """Show error state in detail view."""
        self._detail_error_lbl.setText(f"Error: {error}")
        self._detail_error_lbl.show()
        self._detail_display.hide()
        self._detail_empty_lbl.hide()
        self._detail_loading_lbl.hide()

    def set_list_loading(self, loading: bool) -> None:
        """Show/hide loading state in list view."""
        if loading:
            # Show different loading text for search vs normal loading
            if self._current_search_query:
                self._list_loading_lbl.setText(f"Searching for \"{self._current_search_query}\"…")
                self._list_loading_lbl.setAccessibleName("Searching conversations")
            else:
                self._list_loading_lbl.setText("Loading conversations…")
                self._list_loading_lbl.setAccessibleName("Loading conversations")
        self._list_loading_lbl.setVisible(loading)
        self._list_view.setVisible(not loading)
        self._list_empty_lbl.setVisible(False)

    def clear_selection(self) -> None:
        """Clear the current selection."""
        self._list_view.clearSelection()
        self._selected_conversation_id = None
        self._detail_title_lbl.setText("Select a conversation")
        self._detail_display.hide()
        self._detail_empty_lbl.show()
        self._detail_loading_lbl.hide()
        self._detail_error_lbl.hide()

    def _setup_tab_order(self) -> None:
        """Set explicit tab order for logical keyboard navigation."""
        # Order: dismiss button -> search input -> clear search -> list view -> detail display ->
        # list prev/next -> detail prev/next
        self.setTabOrder(self._dismiss_btn, self._search_input)
        self.setTabOrder(self._search_input, self._search_clear_btn)
        self.setTabOrder(self._search_clear_btn, self._list_view)
        self.setTabOrder(self._list_view, self._detail_display)
        self.setTabOrder(self._detail_display, self._list_prev_btn)
        self.setTabOrder(self._list_prev_btn, self._list_next_btn)
        self.setTabOrder(self._list_next_btn, self._detail_prev_btn)
        self.setTabOrder(self._detail_prev_btn, self._detail_next_btn)
        self.setTabOrder(self._detail_next_btn, self._dismiss_btn)

    def eventFilter(self, watched, event):
        """Handle keyboard events for list view and search input."""
        if watched == self._list_view and event.type() == event.Type.KeyPress:
            return self._handle_list_key_press(event)
        elif watched == self._search_input and event.type() == event.Type.KeyPress:
            return self._handle_search_key_press(event)
        elif watched == self._detail_display and event.type() == event.Type.KeyPress:
            return self._handle_detail_key_press(event)
        return super().eventFilter(watched, event)

    def _handle_list_key_press(self, event: QKeyEvent) -> bool:
        """Handle key presses when list view has focus."""
        key = event.key()

        # Enter/Return: activate selected conversation
        if key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            index = self._list_view.currentIndex()
            if index.isValid():
                self._on_list_clicked(index)
                return True

        # Left/Right arrows: navigate list pagination
        elif key == Qt.Key.Key_Left:
            if self._list_prev_btn.isEnabled():
                self._on_page_change("list", -1)
                return True
        elif key == Qt.Key.Key_Right:
            if self._list_next_btn.isEnabled():
                self._on_page_change("list", +1)
                return True

        # Page Up/Page Down: jump 5 pages
        elif key == Qt.Key.Key_PageUp:
            if self._list_prev_btn.isEnabled():
                new_page = max(0, self._current_list_page - 5)
                self.list_page_requested.emit(new_page)
                return True
        elif key == Qt.Key.Key_PageDown:
            if self._list_next_btn.isEnabled():
                new_page = min(self._total_list_pages - 1, self._current_list_page + 5)
                self.list_page_requested.emit(new_page)
                return True

        return False

    def _handle_search_key_press(self, event: QKeyEvent) -> bool:
        """Handle key presses when search input has focus."""
        key = event.key()

        # Escape: clear search
        if key == Qt.Key.Key_Escape:
            self._search_input.clear()
            return True

        return False

    def _handle_detail_key_press(self, event: QKeyEvent) -> bool:
        """Handle key presses when detail display has focus."""
        key = event.key()
        modifiers = event.modifiers()

        # Ctrl+Left/Ctrl+Right: navigate detail pagination
        if modifiers & Qt.KeyboardModifier.ControlModifier:
            if key == Qt.Key.Key_Left:
                if self._detail_prev_btn.isEnabled():
                    self._on_page_change("detail", -1)
                    return True
            elif key == Qt.Key.Key_Right:
                if self._detail_next_btn.isEnabled():
                    self._on_page_change("detail", +1)
                    return True

        # Page Up/Page Down: jump 5 pages in detail
        elif key == Qt.Key.Key_PageUp:
            if self._detail_prev_btn.isEnabled():
                new_page = max(0, self._current_detail_page - 5)
                self.detail_page_requested.emit(new_page)
                return True
        elif key == Qt.Key.Key_PageDown:
            if self._detail_next_btn.isEnabled():
                new_page = min(self._total_detail_pages - 1, self._current_detail_page + 5)
                self.detail_page_requested.emit(new_page)
                return True

        return False

    def keyPressEvent(self, event: QKeyEvent) -> None:
        """Handle panel-level key presses (e.g., Escape to dismiss)."""
        if event.key() == Qt.Key.Key_Escape:
            # Only dismiss if search input is not focused (it handles its own Escape)
            if not self._search_input.hasFocus():
                self.hide()
                event.accept()
                return
        super().keyPressEvent(event)

    # Internal event handlers

    def _on_list_clicked(self, index) -> None:
        item = self._list_model.itemFromIndex(index)
        if item:
            conv_id = item.data(Qt.ItemDataRole.UserRole)
            if conv_id:
                self._selected_conversation_id = conv_id
                self.conversation_selected.emit(conv_id)

    def _on_page_change(self, which: str, delta: int) -> None:
        if which == "list":
            new_page = self._current_list_page + delta
            if 0 <= new_page < self._total_list_pages:
                self.list_page_requested.emit(new_page)
        else:
            new_page = self._current_detail_page + delta
            if 0 <= new_page < self._total_detail_pages:
                self.detail_page_requested.emit(new_page)

    def _on_search_text_changed(self, text: str) -> None:
        # Show/hide clear button based on search text
        self._search_clear_btn.setVisible(bool(text.strip()))
        self._search_timer.start()

    def _emit_search(self) -> None:
        query = self._search_input.text().strip()
        self._current_search_query = query
        self.search_requested.emit(query)

    def _clear_search(self) -> None:
        """Clear the search input and reset search state."""
        self._search_input.clear()
        self._search_clear_btn.hide()
        self._current_search_query = ""
        # Emit empty search to reset list
        self.search_requested.emit("")

    def _on_resume_clicked(self) -> None:
        """Handle Resume Session button click — emit signal with current conversation ID."""
        if self._selected_conversation_id:
            self.hide()
            self.session_resumed.emit(self._selected_conversation_id)

    def _on_dismiss(self) -> None:
        """Handle dismiss button click — hide panel and notify MainWindow."""
        self.hide()
        self.dismissed.emit()

    def keyPressEvent(self, event: QKeyEvent) -> None:
        """Handle panel-level key presses (e.g., Escape to dismiss)."""
        if event.key() == Qt.Key.Key_Escape:
            # Only dismiss if search input is not focused (it handles its own Escape)
            if not self._search_input.hasFocus():
                self.hide()
                self.dismissed.emit()
                event.accept()
                return
        super().keyPressEvent(event)

    @staticmethod
    def _esc(s: str) -> str:
        return (str(s or "").replace("&", "&amp;")
                .replace("<", "&lt;").replace(">", "&gt;")
                .replace("\n", "<br>"))