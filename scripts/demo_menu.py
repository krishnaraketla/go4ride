#!/usr/bin/env python3
"""Menu-driven API demo (Typer). API must be running: ./scripts/dev.sh run"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import typer

sys.path.insert(0, str(Path(__file__).resolve().parent))

from demo_session import (  # noqa: E402
    DemoSession,
    SESSION_PATH,
    step_addresses,
    step_auth,
    step_cancel,
    step_create_ride,
    step_email_verify,
    step_estimate,
    step_geocode,
    step_health,
    step_history,
    step_insights,
    step_invoice,
    step_logout,
    step_partner_interest,
    step_payment_methods,
    step_profile,
    step_promo,
    step_referral,
    step_refresh,
    step_repeat,
    step_ride_status,
    step_settings,
    step_stats,
    step_wallet,
    step_ws_listen,
)

app = typer.Typer(
    help="Interactive Go4Ride API demo. Start API first: ./scripts/dev.sh run",
    no_args_is_help=False,
)

MENU = """
Go4Ride — interactive menu
  Rides
  1) Health        2) Auth           3) Geocode
  4) Estimate      5) Create ride    6) Ride status
  7) WS listen     8) Cancel ride
  Profile & growth
  a) Refresh       b) Profile        c) Insights
  d) Addresses     e) Settings       f) Wallet
  g) Promo         h) Referral       i) Email verify
  j) Payments      k) Partner lead
  Bookings
  l) History       m) Repeat ride    n) Invoice
  o) Stats         p) Logout
  s) Session       r) Reset          q) Quit
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
    _interactive_loop()


@app.command("health")
def health_cmd() -> None:
    _print_result("Health", step_health())


@app.command("auth")
def auth_cmd() -> None:
    _run("Auth", step_auth, DemoSession.load())


@app.command("refresh")
def refresh_cmd() -> None:
    _run("Refresh", step_refresh, DemoSession.load())


@app.command("insights")
def insights_cmd() -> None:
    _run("Insights", step_insights, DemoSession.load())


@app.command("ws-listen")
def ws_listen_cmd() -> None:
    import asyncio

    session = DemoSession.load()
    if not session.ride_id:
        typer.secho("Create a ride first.", fg=typer.colors.RED)
        raise typer.Exit(1)

    typer.echo(f"Listening on {session.ws_url} (Ctrl+C to stop)\n")

    def on_event(payload: dict) -> None:
        typer.echo(json.dumps(payload, indent=2))

    try:
        asyncio.run(step_ws_listen(session, on_event=on_event))
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
    typer.echo("Go4Ride — menu demo")
    typer.echo("Ensure API is running: ./scripts/dev.sh run\n")

    steps: dict[str, tuple[str, object]] = {
        "1": ("Health", lambda: step_health()),
        "2": ("Auth", lambda s=session: step_auth(s)),
        "3": ("Geocode", lambda s=session: step_geocode(s)),
        "4": ("Estimate", lambda s=session: step_estimate(s)),
        "5": ("Create ride", lambda s=session: step_create_ride(s)),
        "6": ("Ride status", lambda s=session: step_ride_status(s)),
        "8": ("Cancel", lambda s=session: step_cancel(s)),
        "a": ("Refresh", lambda s=session: step_refresh(s)),
        "b": ("Profile", lambda s=session: step_profile(s)),
        "c": ("Insights", lambda s=session: step_insights(s)),
        "d": ("Addresses", lambda s=session: step_addresses(s)),
        "e": ("Settings", lambda s=session: step_settings(s)),
        "f": ("Wallet", lambda s=session: step_wallet(s)),
        "g": ("Promo", lambda s=session: step_promo(s)),
        "h": ("Referral", lambda s=session: step_referral(s)),
        "i": ("Email verify", lambda s=session: step_email_verify(s)),
        "j": ("Payment methods", lambda s=session: step_payment_methods(s)),
        "k": ("Partner lead", lambda s=session: step_partner_interest(s)),
        "l": ("History", lambda s=session: step_history(s)),
        "m": ("Repeat ride", lambda s=session: step_repeat(s)),
        "n": ("Invoice", lambda s=session: step_invoice(s)),
        "o": ("Stats", lambda s=session: step_stats(s)),
        "p": ("Logout", lambda s=session: step_logout(s)),
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

            typer.echo("WS listen (Ctrl+C to stop)")
            try:
                asyncio.run(step_ws_listen(session, on_event=on_event))
            except KeyboardInterrupt:
                typer.echo("\nStopped listening.")
            if session.ride_id:
                session.completed_ride_id = session.ride_id
                session.save()
            continue

        if choice not in steps:
            typer.secho("Invalid choice.", fg=typer.colors.YELLOW)
            continue

        label, fn = steps[choice]
        try:
            result = fn() if label == "Health" else fn()
            _print_result(label, result)
            if label == "Create ride" and session.ride_id:
                session.completed_ride_id = session.ride_id
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
