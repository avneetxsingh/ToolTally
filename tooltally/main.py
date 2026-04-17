#!/usr/bin/env python3
# ── main.py ──────────────────────────────────────────────────────────
# ToolTally entry point. Just delegates to main_ui_2.App so you can
# launch the whole system with:
#
#     python3 main.py
#
# All hardware init (servos + camera) happens inside App.__init__.
# ─────────────────────────────────────────────────────────────────────

from main_ui_2 import App


def main():
    app = App()
    app.protocol("WM_DELETE_WINDOW", app.on_close)
    try:
        app.mainloop()
    except KeyboardInterrupt:
        print("\n[MAIN] Ctrl-C — shutting down")
        app.on_close()


if __name__ == "__main__":
    main()
