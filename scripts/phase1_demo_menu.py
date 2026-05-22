#!/usr/bin/env python3
"""Menu-driven Phase 1 demo (Typer). API must be running: ./scripts/dev.sh run"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import typer

# Allow `python scripts/phase1_demo_menu.py` from repo root
sys.path.insert(0, str(Path(__file__).resolve().parent))

from demo_session import (  # noqa: E402
    DemoSession,
    SESSION_PATH,
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

app = typer.Typer(
    help="Interactive Phase 1 API demo. Start API first: ./scripts/dev.sh run",
    no_args_is_help=False,
)

MENU = """
Go4Ride Phase 1 — interactive menu
  1) Health        2) Auth           3) Geocode
  4) Estimate      5) Create ride    6) Ride status
  7) WS listen     8) Cancel ride    9) Stats
  s) Session       r) Reset session  q) Quit
"""


def _print_result(label: str, data: object) -> None:
    typer.echo(f"\n=== {label} ===")
    typer.echo(json.dumps(data, indent=2, default=str))


def _run(step_name: str, fn, session: DemoSession) -> None:
    try:
        result = fn(session) if session is not None else fn()
        _print_result(step_name, result)
    except Exception as exc:
        typer.secho(f"Error: {exc}", fg=typer.colors.RED, err=True)


@app.command("menu")
def menu_command() -> None:
    """Interactive numbered menu (default)."""
    _interactive_loop()


@app.command("health")
def health_cmd() -> None:
    _print_result("Health", step_health())


@app.command("auth")
def auth_cmd() -> None:
    session = DemoSession.load()
    _run("Auth", step_auth, session)


@app.command("geocode")
def geocode_cmd() -> None:
    session = DemoSession.load()
    _run("Geocode", step_geocode, session)


@app.command("estimate")
def estimate_cmd() -> None:
    session = DemoSession.load()
    _run("Estimate", step_estimate, session)


@app.command("create-ride")
def create_ride_cmd() -> None:
    session = DemoSession.load()
    _run("Create ride", step_create_ride, session)


@app.command("status")
def status_cmd() -> None:
    session = DemoSession.load()
    _run("Ride status", step_ride_status, session)


@app.command("cancel")
def cancel_cmd() -> None:
    session = DemoSession.load()
    _run("Cancel", step_cancel, session)


@app.command("stats")
def stats_cmd() -> None:
    session = DemoSession.load()
    _run("Stats", step_stats, session)


@app.command("ws-listen")
def ws_listen_cmd() -> None:
    """Listen for WebSocket events until Ctrl+C."""
    import asyncio

    session = DemoSession.load()
    if not session.ride_id:
        typer.secho("Create a ride first.", fg=typer.colors.RED)
        raise typer.Exit(1)

    typer.echo(f"Listening on {session.ws_url} (Ctrl+C to stop)\n")

    def on_event(payload: dict) -> None:
        typer.echo(json.dumps(payload, indent=2))

    async def run() -> None:
        await step_ws_listen(session, on_event=on_event)

    try:
        asyncio.run(run())
    except KeyboardInterrupt:
        typer.echo("\nStopped listening.")


@app.command("session")
def session_cmd() -> None:
    session = DemoSession.load()
    _print_result("Session", session.summary())
    if SESSION_PATH.exists():
        typer.echo(f"\nSaved at: {SESSION_PATH}")


def _interactive_loop() -> None:
    session = DemoSession.load()
    typer.echo("Go4Ride Phase 1 — menu demo")
    typer.echo("Ensure API is running: ./scripts/dev.sh run\n")

    steps: dict[str, tuple[str, object]] = {
        "1": ("Health", lambda: step_health()),
        "2": ("Auth", lambda s=session: step_auth(s)),
        "3": ("Geocode", lambda s=session: step_geocode(s)),
        "4": ("Estimate", lambda s=session: step_estimate(s)),
        "5": ("Create ride", lambda s=session: step_create_ride(s)),
        "6": ("Ride status", lambda s=session: step_ride_status(s)),
        "7": ("WS listen", None),
        "8": ("Cancel", lambda s=session: step_cancel(s)),
        "9": ("Stats", lambda s=session: step_stats(s)),
    }

    while True:
        typer.echo(MENU)
        choice = typer.prompt("Choice", default="").strip().lower()

        if choice in ("q", "quit", "exit"):
            typer.echo("Bye.")
            break
        if choice == "s":
            _print_result("Session", session.summary())
            continue
        if choice == "r":
            session = DemoSession()
            if SESSION_PATH.exists():
                SESSION_PATH.unlink()
            typer.echo("Session reset.")
            continue
        if choice == "7":
            import asyncio

            def on_event(payload: dict) -> None:
                typer.echo(json.dumps(payload, indent=2))

            async def run() -> None:
                await step_ws_listen(session, on_event=on_event)

            typer.echo("WS listen (Ctrl+C to stop)")
            try:
                asyncio.run(run())
            except KeyboardInterrupt:
                typer.echo("\nStopped listening.")
            continue

        if choice not in steps:
            typer.secho("Invalid choice.", fg=typer.colors.YELLOW)
            continue

        label, fn = steps[choice]
        if fn is None:
            continue
        try:
            result = fn() if label == "Health" else fn()
            _print_result(label, result)
            session.save()
        except Exception as exc:
            typer.secho(f"Error: {exc}", fg=typer.colors.RED, err=True)


@app.callback(invoke_without_command=True)
def main(ctx: typer.Context) -> None:
    os.chdir(Path(__file__).resolve().parent.parent)
    if ctx.invoked_subcommand is None:
        _interactive_loop()


if __name__ == "__main__":
    app()
