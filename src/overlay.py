import tkinter as tk
import threading
from ctypes import windll
from .advisor import Decision

PRIORITY_COLORS = {
    "URGENT": "#FF4444",
    "BUY":    "#44FF88",
    "SELL":   "#FF8844",
    "ITEM":   "#44CCFF",
    "AUGMENT":"#FFDD00",
    "ECONOMY":"#AAAAFF",
    "INFO":   "#888899",
}

PRIORITY_LABEL = {
    "URGENT": "긴급",
    "BUY":    "구매",
    "SELL":   "매각",
    "ITEM":   "아이템",
    "AUGMENT":"증강",
    "ECONOMY":"경제",
    "INFO":   "",
}


class Overlay:
    def __init__(self, x: int, y: int, width: int, height: int, alpha: float = 0.88):
        self.x = x
        self.y = y
        self.width = width
        self.height = height
        self.alpha = alpha
        self.root = None
        self._lock = threading.Lock()
        self._pending: list[Decision] = []
        self._status = "시작 중..."
        self._last_update = ""

    def start(self):
        self.root = tk.Tk()
        self.root.overrideredirect(True)
        self.root.attributes("-topmost", True)
        self.root.attributes("-alpha", self.alpha)
        self.root.geometry(f"{self.width}x{self.height}+{self.x}+{self.y}")
        self.root.configure(bg="#090912")
        self._make_clickthrough()
        self._build_ui()
        self.root.after(400, self._poll)
        self.root.mainloop()

    def _make_clickthrough(self):
        try:
            hwnd = windll.user32.GetParent(self.root.winfo_id())
            style = windll.user32.GetWindowLongW(hwnd, -20)
            style |= 0x00000020  # WS_EX_TRANSPARENT
            style |= 0x00000080  # WS_EX_TOOLWINDOW
            windll.user32.SetWindowLongW(hwnd, -20, style)
        except Exception:
            pass

    def _build_ui(self):
        # 헤더
        hdr = tk.Frame(self.root, bg="#111126", height=38)
        hdr.pack(fill=tk.X)
        hdr.pack_propagate(False)

        tk.Label(hdr, text="TFT ADVISOR", bg="#111126",
                 fg="#00FFAA", font=("Consolas", 11, "bold")).pack(side=tk.LEFT, padx=10, pady=7)

        self.status_lbl = tk.Label(hdr, text="", bg="#111126",
                                   fg="#555577", font=("Consolas", 7))
        self.status_lbl.pack(side=tk.RIGHT, padx=8, pady=7)

        # 스크롤 가능한 캔버스
        container = tk.Frame(self.root, bg="#090912")
        container.pack(fill=tk.BOTH, expand=True)

        self.canvas = tk.Canvas(container, bg="#090912", highlightthickness=0,
                                bd=0)
        scrollbar = tk.Scrollbar(container, orient="vertical", command=self.canvas.yview)
        self.canvas.configure(yscrollcommand=scrollbar.set)

        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        self.inner = tk.Frame(self.canvas, bg="#090912")
        self.canvas_window = self.canvas.create_window((0, 0), window=self.inner, anchor="nw")
        self.inner.bind("<Configure>", self._on_frame_configure)
        self.canvas.bind("<Configure>", self._on_canvas_configure)

    def _on_frame_configure(self, _):
        self.canvas.configure(scrollregion=self.canvas.bbox("all"))

    def _on_canvas_configure(self, event):
        self.canvas.itemconfig(self.canvas_window, width=event.width)

    def update(self, decisions: list[Decision], status: str = ""):
        with self._lock:
            self._pending = decisions[:]
            self._status = status

    def _poll(self):
        with self._lock:
            decisions = self._pending[:]
            status = self._status

        key = status + str(len(decisions))
        if key != self._last_update:
            self._render(decisions, status)
            self._last_update = key

        self.root.after(400, self._poll)

    def _render(self, decisions: list[Decision], status: str):
        for w in self.inner.winfo_children():
            w.destroy()

        self.status_lbl.config(text=status)

        if not decisions:
            tk.Label(self.inner, text="화면 분석 대기 중...",
                     bg="#090912", fg="#333355",
                     font=("Consolas", 9)).pack(pady=30)
            return

        for dec in decisions:
            self._card(dec)

    def _card(self, dec: Decision):
        color = PRIORITY_COLORS.get(dec.priority, "#888899")
        label = PRIORITY_LABEL.get(dec.priority, "")

        is_info = dec.priority == "INFO"
        bg = "#0D0D1E" if is_info else "#13132A"

        card = tk.Frame(self.inner, bg=bg, bd=0)
        card.pack(fill=tk.X, padx=3, pady=2)

        # 왼쪽 색상 막대
        tk.Frame(card, bg=color, width=3).pack(side=tk.LEFT, fill=tk.Y)

        body = tk.Frame(card, bg=bg)
        body.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=7, pady=4)

        # 태그 + EV 점수
        top_row = tk.Frame(body, bg=bg)
        top_row.pack(fill=tk.X)

        if label:
            tk.Label(top_row, text=f" {label} ", bg=color, fg="#000000",
                     font=("Consolas", 7, "bold"), padx=2).pack(side=tk.LEFT)

        if dec.ev is not None:
            ev_color = "#44FF88" if dec.ev >= 0 else "#FF6644"
            tk.Label(top_row, text=f"  EV {dec.ev:+.2f}", bg=bg, fg=ev_color,
                     font=("Consolas", 7)).pack(side=tk.LEFT, padx=4)

        # 액션 텍스트
        fg = color if not is_info else "#777788"
        tk.Label(body, text=dec.action, bg=bg, fg=fg,
                 font=("Consolas", 9, "bold" if not is_info else "normal"),
                 wraplength=self.width - 40, justify=tk.LEFT, anchor=tk.W
                 ).pack(fill=tk.X, pady=(2, 0))

        # 상세 설명
        if dec.detail:
            tk.Label(body, text=dec.detail, bg=bg, fg="#666677",
                     font=("Consolas", 7),
                     wraplength=self.width - 40, justify=tk.LEFT, anchor=tk.W
                     ).pack(fill=tk.X)

        # 구분선 (INFO는 얇게)
        sep_color = "#1A1A30" if is_info else "#1E1E38"
        tk.Frame(self.inner, bg=sep_color, height=1).pack(fill=tk.X, padx=3)
