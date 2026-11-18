from __future__ import annotations

import argparse
import io
import os
import sys
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

from xau_collector.config import AppSettings, load_settings
from xau_collector.domain.market import InstrumentIdentity
from xau_collector.errors import CollectorError
from xau_collector.infrastructure.csv_market_repository import CsvMarketDataRepository
from xau_collector.infrastructure.csv_store import CsvM1Store
from xau_collector.infrastructure.metatrader import MetaTraderGateway
from xau_collector.infrastructure.postgres_history_importer import (
    PostgresHistoricalImporter,
    discover_historical_csvs,
)
from xau_collector.infrastructure.postgres_market_repository import PostgresMarketDataRepository
from xau_collector.infrastructure.postgres_snapshot_repository import (
    load_analysis_snapshot,
    load_source_snapshot,
)
from xau_collector.infrastructure.postgres_technical_audit_store import PostgresTechnicalAuditStore
from xau_collector.reporting import render_json, write_json_report
from xau_collector.services.consolidation_poi import ConsolidationPoiBrain
from xau_collector.services.discovery import DiscoveryService
from xau_collector.services.doctor import DoctorService
from xau_collector.services.historical_multi_timeframe import HistoricalMultiTimeframeRunner
from xau_collector.services.history_download import HistoryDownloadService
from xau_collector.services.history_probe import HistoryProbeService
from xau_collector.services.history_source_comparison import HistoricalSourceComparisonService
from xau_collector.services.key_levels import KeyLevelsBrain
from xau_collector.services.m1_collection import M1CollectionService
from xau_collector.services.m1_quality import M1QualityValidator
from xau_collector.services.market_data_quality_brain import MarketDataQualityBrain
from xau_collector.services.session_brain import SessionBrain
from xau_collector.services.session_calendar import Mt5QuoteSessionCalendar
from xau_collector.services.symbol_resolver import SymbolResolver
from xau_collector.services.technical_structure import (
    H1StructureBrain,
    H4StructureBrain,
    M5ReactionBrain,
    M15PoiConfirmationBrain,
)


# Configura UTF-8 en consola para mostrar reportes y errores en español correctamente.
def _configure_console_encoding() -> None:
    """Ensure JSON and Spanish diagnostics survive legacy Windows code pages."""
    for stream_name in ("stdout", "stderr"):
        stream = getattr(sys, stream_name)
        if isinstance(stream, io.TextIOBase) and hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")


# Define los comandos y argumentos públicos de la interfaz de consola.
def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="xau-collector")
    subcommands = parser.add_subparsers(dest="command", required=True)
    for name in (
        "doctor",
        "discover",
        "brain-data-quality",
        "brain-technical-structure",
        "brain-h1-structure",
        "brain-m15-confirmation",
        "brain-m5-observation",
        "brain-key-levels",
        "brain-consolidation-poi",
    ):
        command = subcommands.add_parser(name)
        command.add_argument(
            "--config", type=Path, default=Path("config.toml"), help="Archivo TOML"
        )
        command.add_argument("--save", action="store_true", help="Guardar reporte JSON")
    collection = subcommands.add_parser("download-m1")
    collection.add_argument("--config", type=Path, default=Path("config.toml"), help="Archivo TOML")
    collection.add_argument(
        "--from", dest="start_date", required=True, help="Fecha UTC: YYYY-MM-DD"
    )
    collection.add_argument("--to", dest="end_date", required=True, help="Fecha UTC: YYYY-MM-DD")
    collection.add_argument("--save", action="store_true", help="Guardar reporte JSON")
    history = subcommands.add_parser("download-history")
    history.add_argument("--config", type=Path, default=Path("config.toml"), help="Archivo TOML")
    history.add_argument("--timeframe", required=True, choices=("H4", "H1", "M15", "M5"))
    history.add_argument("--from", dest="start_date", required=True, help="Fecha UTC: YYYY-MM-DD")
    history.add_argument("--to", dest="end_date", required=True, help="Fecha UTC: YYYY-MM-DD")
    analysis = subcommands.add_parser("analyze-history")
    analysis.add_argument("--root", type=Path, default=Path("data/raw"), help="Históricos locales")
    analysis.add_argument("--at", dest="cutoff", help="Corte UTC: YYYY-MM-DDTHH:MM")
    session_analysis = subcommands.add_parser("analyze-sessions-history")
    session_analysis.add_argument("--root", type=Path, default=Path("data/raw"))
    session_analysis.add_argument("--at", required=True, help="Corte UTC: YYYY-MM-DDTHH:MM")
    import_history = subcommands.add_parser("import-history")
    import_history.add_argument("--root", type=Path, default=Path("data/raw"))
    import_history.add_argument("--symbol", default="XAUUSDm")
    import_history.add_argument("--canonical-symbol", default="XAUUSD")
    import_history.add_argument("--broker", default="Exness")
    import_history.add_argument("--server", default="Exness Technologies Ltd")
    import_history.add_argument("--source-name", default="mt5_csv")
    import_history.add_argument("--digits", type=int, default=3)
    import_history.add_argument("--point", type=float, default=0.001)
    subcommands.add_parser("verify-history-import")
    comparison = subcommands.add_parser("compare-history-sources")
    comparison.add_argument("--root", type=Path, default=Path("data/raw"))
    comparison.add_argument("--timeframe", choices=("ALL", "H4", "H1", "M15", "M5"), default="ALL")
    comparison.add_argument("--lookback-bars", type=int, default=180)
    full_comparison = subcommands.add_parser("compare-multitimeframe-sources")
    full_comparison.add_argument("--root", type=Path, default=Path("data/raw"))
    full_comparison.add_argument("--at", required=True, help="Corte UTC: YYYY-MM-DDTHH:MM")
    persist_analysis = subcommands.add_parser("persist-history-analysis")
    persist_analysis.add_argument("--root", type=Path, default=Path("data/raw"))
    persist_analysis.add_argument("--at", required=True, help="Corte UTC: YYYY-MM-DDTHH:MM")
    verify_analysis = subcommands.add_parser("verify-technical-analysis")
    verify_analysis.add_argument("--analysis-run-id", required=True)
    replay_analysis = subcommands.add_parser("replay-original-analysis")
    replay_analysis.add_argument("--analysis-run-id", required=True)
    reanalyze_current = subcommands.add_parser("reanalyze-current-analysis")
    reanalyze_current.add_argument("--analysis-run-id", required=True)
    validate_postgres = subcommands.add_parser("validate-postgres-stage")
    validate_postgres.add_argument("--root", type=Path, default=Path("data/raw"))
    validate_postgres.add_argument("--at", required=True, help="Corte UTC: YYYY-MM-DDTHH:MM")
    return parser


# Construye una ruta de reporte única usando la hora UTC de la ejecución.
def _report_path(settings: AppSettings, report_name: str) -> Path:
    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    return settings.output.reports_directory / f"{report_name}_{timestamp}.json"


# Muestra un resultado y opcionalmente conserva una copia JSON en disco.
def _emit(payload: dict[str, object], settings: AppSettings, name: str, save: bool) -> None:
    print(render_json(payload))
    if save:
        destination = _report_path(settings, name)
        write_json_report(payload, destination)
        print(f"Reporte guardado: {destination}", file=sys.stderr)


# Convierte una fecha de consola en el límite inicial o final UTC de ese día.
def _parse_utc_date(value: str, is_end: bool) -> datetime:
    try:
        parsed = datetime.strptime(value, "%Y-%m-%d").replace(tzinfo=UTC)
    except ValueError as exc:
        raise CollectorError("Las fechas deben usar el formato YYYY-MM-DD") from exc
    return parsed if not is_end else parsed.replace(hour=23, minute=59, second=59)


# Ejecuta el comando solicitado y devuelve un código de salida para PowerShell.
def main(argv: Sequence[str] | None = None) -> int:
    _configure_console_encoding()
    args = _parser().parse_args(argv)
    try:
        if args.command == "analyze-history":
            cutoff = (
                datetime.strptime(args.cutoff, "%Y-%m-%dT%H:%M").replace(tzinfo=UTC)
                if args.cutoff
                else None
            )
            analysis = HistoricalMultiTimeframeRunner().run(args.root, cutoff)
            print(
                render_json(
                    {
                        "explanation": analysis.explanation,
                        "h4_h1_alignment": analysis.h4_h1_alignment,
                        "m15_context": analysis.m15_context,
                        "m5_context": analysis.m5_context,
                        "confirmation": {
                            "m15_state": analysis.confirmation.m15_state,
                            "m5_sweep": analysis.confirmation.m5_sweep,
                            "m5_reaction": analysis.confirmation.m5_reaction,
                            "m5_body_break": analysis.confirmation.m5_body_break,
                        },
                        "targets_above": analysis.targets_above,
                        "targets_below": analysis.targets_below,
                        "key_levels": [
                            {"period": level.period, "high": level.high, "low": level.low}
                            for level in analysis.key_levels
                        ],
                    }
                )
            )
            return 0
        if args.command == "analyze-sessions-history":
            cutoff = datetime.strptime(args.at, "%Y-%m-%dT%H:%M").replace(tzinfo=UTC)
            report = SessionBrain().run(
                CsvMarketDataRepository(args.root),
                InstrumentIdentity("Exness", "Exness Technologies Ltd", "XAUUSDm", "mt5_csv"),
                cutoff,
            )
            print(render_json(report.to_dict()))
            return 0
        if args.command == "import-history":
            importer = PostgresHistoricalImporter(os.environ.get("XAU_DATABASE_URL", ""))
            identity = InstrumentIdentity(args.broker, args.server, args.symbol, args.source_name)
            reports = tuple(
                importer.import_csv(
                    source,
                    identity,
                    args.canonical_symbol,
                    args.digits,
                    args.point,
                    timeframe,
                )
                for timeframe, source in discover_historical_csvs(args.root)
            )
            print(render_json({"imports": [report.to_dict() for report in reports]}))
            return 0
        if args.command == "verify-history-import":
            report = PostgresHistoricalImporter(
                os.environ.get("XAU_DATABASE_URL", "")
            ).verification_report()
            print(render_json(report))
            return 0
        if args.command == "compare-history-sources":
            identity = InstrumentIdentity("Exness", "Exness Technologies Ltd", "XAUUSDm", "mt5_csv")
            timeframes = ("H4", "H1", "M15", "M5") if args.timeframe == "ALL" else (args.timeframe,)
            comparisons = tuple(
                HistoricalSourceComparisonService().compare(
                    CsvMarketDataRepository(args.root),
                    PostgresMarketDataRepository(os.environ.get("XAU_DATABASE_URL", "")),
                    identity,
                    timeframe,
                    lookback_bars=args.lookback_bars,
                )
                for timeframe in timeframes
            )
            print(
                render_json({"comparisons": [comparison.to_dict() for comparison in comparisons]})
            )
            return 0 if all(comparison.equivalent for comparison in comparisons) else 2
        if args.command == "compare-multitimeframe-sources":
            cutoff = datetime.strptime(args.at, "%Y-%m-%dT%H:%M").replace(tzinfo=UTC)
            equivalent, differences = HistoricalSourceComparisonService().compare_multitimeframe(
                CsvMarketDataRepository(args.root),
                PostgresMarketDataRepository(os.environ.get("XAU_DATABASE_URL", "")),
                InstrumentIdentity("Exness", "Exness Technologies Ltd", "XAUUSDm", "mt5_csv"),
                cutoff,
            )
            print(render_json({"equivalent": equivalent, "differences": differences}))
            return 0 if equivalent else 2
        if args.command == "persist-history-analysis":
            cutoff = datetime.strptime(args.at, "%Y-%m-%dT%H:%M").replace(tzinfo=UTC)
            analysis = HistoricalMultiTimeframeRunner().run(args.root, cutoff)
            persisted = PostgresTechnicalAuditStore(os.environ.get("XAU_DATABASE_URL", "")).persist(
                analysis,
                InstrumentIdentity("Exness", "Exness Technologies Ltd", "XAUUSDm", "mt5_csv"),
                cutoff,
                {
                    "h4_lookback_bars": 180,
                    "h1_lookback_bars": 360,
                    "m15_lookback_bars": 480,
                    "m5_lookback_bars": 576,
                },
            )
            print(render_json(persisted.to_dict()))
            return 0
        if args.command == "verify-technical-analysis":
            report = PostgresTechnicalAuditStore(
                os.environ.get("XAU_DATABASE_URL", "")
            ).verification_report(UUID(args.analysis_run_id))
            print(render_json(report))
            return 0
        if args.command in ("replay-original-analysis", "reanalyze-current-analysis"):
            database_url = os.environ.get("XAU_DATABASE_URL", "")
            snapshot_repository, identity, cutoff = load_analysis_snapshot(
                database_url, UUID(args.analysis_run_id)
            )
            repository = (
                snapshot_repository
                if args.command == "replay-original-analysis"
                else PostgresMarketDataRepository(database_url)
            )
            analysis = HistoricalMultiTimeframeRunner().run_from_repository(
                repository, identity, cutoff
            )
            print(
                render_json(
                    {
                        "mode": "ORIGINAL_SNAPSHOT"
                        if args.command == "replay-original-analysis"
                        else "CURRENT_REVISIONS",
                        "analysis_run_id": args.analysis_run_id,
                        "data_cutoff_utc": cutoff.isoformat(),
                        "explanation": analysis.explanation,
                        "confirmation": {
                            "m15_state": analysis.confirmation.m15_state,
                            "m15_confirmed_at_utc": (
                                analysis.confirmation.m15_confirmed_at_utc.isoformat()
                            if analysis.confirmation.m15_confirmed_at_utc
                                else None
                            ),
                            "m5_sweep": analysis.confirmation.m5_sweep,
                            "m5_reaction": analysis.confirmation.m5_reaction,
                            "m5_body_break": analysis.confirmation.m5_body_break,
                        },
                        "consolidation_count": len(analysis.consolidations),
                    }
                )
            )
            return 0
        if args.command == "validate-postgres-stage":
            cutoff = datetime.strptime(args.at, "%Y-%m-%dT%H:%M").replace(tzinfo=UTC)
            identity = InstrumentIdentity("Exness", "Exness Technologies Ltd", "XAUUSDm", "mt5_csv")
            csv_repository = CsvMarketDataRepository(args.root)
            postgres_repository = PostgresMarketDataRepository(
                os.environ.get("XAU_DATABASE_URL", "")
            )
            equivalent, differences = HistoricalSourceComparisonService().compare_multitimeframe(
                csv_repository, postgres_repository, identity, cutoff
            )
            if not equivalent:
                print(render_json({"equivalent": False, "differences": differences}))
                return 2
            store = PostgresTechnicalAuditStore(os.environ.get("XAU_DATABASE_URL", ""))
            source_snapshot_id = store.capture_snapshot(identity, cutoff)
            snapshot_repository, snapshot_identity, snapshot_cutoff = load_source_snapshot(
                os.environ.get("XAU_DATABASE_URL", ""), source_snapshot_id
            )
            analysis = HistoricalMultiTimeframeRunner().run_from_repository(
                snapshot_repository, snapshot_identity, snapshot_cutoff
            )
            persisted = store.persist(
                analysis,
                snapshot_identity,
                snapshot_cutoff,
                {
                    "h4_lookback_bars": 180,
                    "h1_lookback_bars": 360,
                    "m15_lookback_bars": 480,
                    "m5_lookback_bars": 576,
                },
                source_snapshot_id,
            )
            print(
                render_json(
                    {
                        "equivalent": True,
                        "persisted": persisted.to_dict(),
                        "verification": store.verification_report(persisted.analysis_run_id),
                    }
                )
            )
            return 0
        settings = load_settings(args.config)
        if args.command == "doctor":
            report = DoctorService().run(settings)
            _emit(report.to_dict(), settings, "doctor", args.save)
            return 0 if report.healthy else 2

        gateway = MetaTraderGateway(settings.mt5)
        if args.command == "brain-data-quality":
            calendar = Mt5QuoteSessionCalendar.from_csv(
                settings.sessions.snapshot_path,
                settings.symbol.real_name or "XAUUSDm",
            )
            calendar.require_fresh(datetime.now(UTC))
            report = MarketDataQualityBrain(
                gateway,
                SymbolResolver(),
                calendar,
                M1QualityValidator(calendar),
            ).run(settings)
            _emit(report.to_dict(), settings, "brain_data_quality", args.save)
            return 0
        if args.command == "brain-technical-structure":
            report = H4StructureBrain(gateway, SymbolResolver()).run(
                settings.symbol.logical_name,
                settings.symbol.aliases,
                settings.symbol.real_name,
            )
            _emit(report.to_dict(), settings, "brain_technical_structure", args.save)
            return 0
        if args.command == "brain-h1-structure":
            report = H1StructureBrain(gateway, SymbolResolver()).run(
                settings.symbol.logical_name,
                settings.symbol.aliases,
                settings.symbol.real_name,
            )
            _emit(report.to_dict(), settings, "brain_h1_structure", args.save)
            return 0
        if args.command == "brain-m15-confirmation":
            h1_brain = H1StructureBrain(gateway, SymbolResolver())
            report = M15PoiConfirmationBrain(gateway, SymbolResolver(), h1_brain).run(
                settings.symbol.logical_name,
                settings.symbol.aliases,
                settings.symbol.real_name,
            )
            _emit(report.to_dict(), settings, "brain_m15_confirmation", args.save)
            return 0
        if args.command == "brain-m5-observation":
            h1_brain = H1StructureBrain(gateway, SymbolResolver())
            m15_brain = M15PoiConfirmationBrain(gateway, SymbolResolver(), h1_brain)
            report = M5ReactionBrain(gateway, SymbolResolver(), m15_brain).run(
                settings.symbol.logical_name,
                settings.symbol.aliases,
                settings.symbol.real_name,
            )
            _emit(report.to_dict(), settings, "brain_m5_observation", args.save)
            return 0
        if args.command == "brain-key-levels":
            report = KeyLevelsBrain(gateway, SymbolResolver()).run(
                settings.symbol.logical_name, settings.symbol.aliases, settings.symbol.real_name
            )
            _emit(report.to_dict(), settings, "brain_key_levels", args.save)
            return 0
        if args.command == "brain-consolidation-poi":
            report = ConsolidationPoiBrain(gateway, SymbolResolver()).run(
                settings.symbol.logical_name, settings.symbol.aliases, settings.symbol.real_name
            )
            _emit(report.to_dict(), settings, "brain_consolidation_poi", args.save)
            return 0
        if args.command == "download-m1":
            calendar = Mt5QuoteSessionCalendar.from_csv(
                settings.sessions.snapshot_path,
                settings.symbol.real_name or "XAUUSDm",
            )
            calendar.require_fresh(datetime.now(UTC))
            report = M1CollectionService(
                gateway,
                SymbolResolver(),
                M1QualityValidator(calendar),
                CsvM1Store(),
            ).run(
                settings,
                _parse_utc_date(args.start_date, is_end=False),
                _parse_utc_date(args.end_date, is_end=True),
            )
            _emit(report.to_dict(), settings, "m1_collection", args.save)
            return 0
        if args.command == "download-history":
            gateway.connect()
            try:
                symbol = SymbolResolver().resolve(
                    gateway.list_symbols(),
                    settings.symbol.logical_name,
                    settings.symbol.aliases,
                    settings.symbol.real_name,
                )
            finally:
                gateway.close()
            path = HistoryDownloadService(gateway, CsvM1Store()).download(
                symbol.name,
                args.timeframe,
                _parse_utc_date(args.start_date, False),
                _parse_utc_date(args.end_date, True),
                settings.storage.raw_m1_directory.parent,
            )
            print(path)
            return 0
        report = DiscoveryService(gateway, SymbolResolver(), HistoryProbeService()).run(settings)
        _emit(report.to_dict(), settings, "data_availability", args.save)
        return 0
    except CollectorError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
