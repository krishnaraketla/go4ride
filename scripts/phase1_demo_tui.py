#!/usr/bin/env python3
"""Textual TUI for Phase 1 API demo. API must be running: ./scripts/dev.sh run"""

from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path

from textual import work
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.widgets import Footer, Header, Log, Static

sys.path.insert(0, str(Path(__file__).resolve().parent))

from demo_session import (  # noqa: E402
    DemoSession,
    step_auth,
    step_cancel,
    step_create_ride,
    step_estimate,
    step_geocode,
    step_health,
    step_ride_status,
    step_stats,
    step_ws_listen,
)

HELP = """[bold]Keys[/]
  [cyan]1[/] Health   [cyan]2[/] Auth       [cyan]3[/] Geocode
  [cyan]4[/] Estimate [cyan]5[/] Create     [cyan]6[/] Status
  [cyan]7[/] WS listen [cyan]8[/] Cancel    [cyan]9[/] Stats
  [cyan]s[/] Session  [cyan]r[/] Reset     [cyan]q[/] Quit
"""


class DemoTUI(App[None]):
    TITLE = "Go4Ride Phase 1 Demo"
    CSS = """
    #session-panel {
        height: 8;
        border: solid green;
        padding: 0 1;
    }
    #help-panel {
        height: auto;
        max-height: 12;
        border: solid blue;
        padding: 0 1;
    }
    #log {
        height: 1fr;
        border: solid yellow;
    }
    """

    BINDINGS = [
        Binding("1", "health", "Health", show=True),
        Binding("2", "auth", "Auth", show=True),
        Binding("3", "geocode", "Geocode", show=True),
        Binding("4", "estimate", "Estimate", show=True),
        Binding("5", "create_ride", "Create", show=True),
        Binding("6", "status", "Status", show=True),
        Binding("7", "ws_listen", "WS", show=True),
        Binding("8", "cancel", "Cancel", show=True),
        Binding("9", "stats", "Stats", show=True),
        Binding("s", "show_session", "Session", show=True),
        Binding("r", "reset_session", "Reset", show=True),
        Binding("q", "quit", "Quit", show=True),
    ]

    def __init__(self) -> None:
        super().__init__()
        self.session = DemoSession.load()
        self._ws_stop: asyncio.Event | None = None
        self._ws_task: asyncio.Task[None] | None = None

    def compose(self) -> ComposeResult:
        yield Header()
        with Vertical():
            yield Static(HELP, id="help-panel")
            yield Static(self._session_text(), id="session-panel")
            yield Log(id="log", highlight=True)
        yield Footer()

    def _session_text(self) -> str:
        s = self.session.summary()
        lines = [
            f"user_id: {s.get('user_id') or '—'}",
            f"ride_id: {s.get('ride_id') or '—'}",
            f"auth: {'yes' if s.get('authenticated') else 'no'}",
        ]
        return "\n".join(lines)

    def _refresh_session_panel(self) -> None:
        self.query_one("#session-panel", Static).update(self._session_text())

    def _log(self, label: str, data: object) -> None:
        log = self.query_one("#log", Log)
        log.write_line(f"=== {label} ===")
        log.write_line(json.dumps(data, indent=2, default=str))

    def _log_error(self, exc: BaseException) -> None:
        self.query_one("#log", Log).write_line(f"[red]Error: {exc}[/]")

    @work(exclusive=True)
    async def _run_step(self, label: str, fn) -> None:
        try:
            if label == "Health":
                result = await asyncio.to_thread(step_health)
            else:
                result = await asyncio.to_thread(fn, self.session)
            self._log(label, result)
            self.session.save()
            self._refresh_session_panel()
        except Exception as exc:
            self._log_error(exc)

    def action_health(self) -> None:
        self._run_step("Health", step_health)

    def action_auth(self) -> None:
        self._run_step("Auth", step_auth)

    def action_geocode(self) -> None:
        self._run_step("Geocode", step_geocode)

    def action_estimate(self) -> None:
        self._run_step("Estimate", step_estimate)

    def action_create_ride(self) -> None:
        self._run_step("Create ride", step_create_ride)

    def action_status(self) -> None:
        self._run_step("Ride status", step_ride_status)

    def action_cancel(self) -> None:
        self._run_step("Cancel", step_cancel)

    def action_stats(self) -> None:
        self._run_step("Stats", step_stats)

    def action_show_session(self) -> None:
        self._log("Session", self.session.summary())

    def action_reset_session(self) -> None:
        from demo_session import SESSION_PATH

        self.session = DemoSession()
        if SESSION_PATH.exists():
            SESSION_PATH.unlink()
        self._refresh_session_panel()
        self.query_one("#log", Log).write_line("Session reset.")

    def action_ws_listen(self) -> None:
        if self._ws_task and not self._ws_task.done():
            if self._ws_stop:
                self._ws_stop.set()
            self.query_one("#log", Log).write_line("Stopping WS listener...")
            return
        self._start_ws_listen()

    @work(exclusive=True)
    async def _start_ws_listen(self) -> None:
        if not self.session.ride_id:
            self._log_error(RuntimeError("Create a ride first (key 5)."))
            return

        log = self.query_one("#log", Log)
        log.write_line(f"WS listen: {self.session.ws_url} (press 7 again to stop)")

        self._ws_stop = asyncio.Event()

        def on_event(payload: dict) -> None:
            self.call_from_thread(
                log.write_line,
                json.dumps(payload, indent=2),
            )

        try:
            await step_ws_listen(
                self.session,
                on_event=on_event,
                stop_event=self._ws_stop,
            )
        except Exception as exc:
            self._log_error(exc)
        finally:
            self._ws_stop = None
            log.write_line("WS listener stopped.")

    def action_quit(self) -> None:
        if self._ws_stop:
            self._ws_stop.set()
        self.exit()


def main() -> None:
    os.chdir(Path(__file__).resolve().parent.parent)
    DemoTUI().run()


if __name__ == "__main__":
    main()
