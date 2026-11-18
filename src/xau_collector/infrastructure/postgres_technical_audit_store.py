from __future__ import annotations

import hashlib
import json
import os
import subprocess
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID, uuid4

from xau_collector.domain.market import AnalysisState, InstrumentIdentity
from xau_collector.errors import ConfigurationError, DependencyUnavailableError
from xau_collector.services.historical_multi_timeframe import HistoricalMultiTimeframeAnalysis


# Identifica una ejecución persistida para recuperar sus resultados y evidencias después.
@dataclass(frozen=True, slots=True)
class PersistedTechnicalAnalysis:
    analysis_run_id: UUID
    source_snapshot_id: UUID
    analyzed_at_utc: datetime

    # Convierte identificadores a texto seguro para la interfaz de consola.
    def to_dict(self) -> dict[str, str]:
        return {
            "analysis_run_id": str(self.analysis_run_id),
            "source_snapshot_id": str(self.source_snapshot_id),
            "analyzed_at_utc": self.analyzed_at_utc.isoformat(),
        }


# Guarda una interpretación técnica como historial inmutable, sin sobrescribir ejecuciones previas.
class PostgresTechnicalAuditStore:
    _algorithm_name = "technical_structure"
    _algorithm_version = "1.0.0"

    # Conserva la URL solo durante la ejecución y exige que proceda del entorno local.
    def __init__(self, database_url: str) -> None:
        if not database_url.strip():
            raise ConfigurationError("Falta XAU_DATABASE_URL para guardar análisis técnico")
        self._database_url = database_url.replace("postgresql+psycopg://", "postgresql://", 1)

    # Persiste una ejecución, sus datos usados y todas las interpretaciones derivadas.
    def persist(
        self,
        analysis: HistoricalMultiTimeframeAnalysis,
        identity: InstrumentIdentity,
        data_cutoff_utc: datetime,
        parameters: dict[str, object],
        source_snapshot_id: UUID | None = None,
    ) -> PersistedTechnicalAnalysis:
        psycopg = _psycopg()
        analyzed_at = datetime.now(UTC)
        with psycopg.connect(self._database_url) as connection, connection.cursor() as cursor:
            symbol_id = _symbol_id(cursor, identity)
            source_revision = code_revision()
            version_id = _algorithm_version_id(
                cursor,
                self._algorithm_name,
                f"{self._algorithm_version}+{source_revision[-12:]}",
                source_revision,
            )
            parameters_hash = _parameters_hash(parameters)
            _ensure_parameters(cursor, parameters_hash, parameters)
            snapshot_id = source_snapshot_id or _insert_snapshot(
                cursor, symbol_id, data_cutoff_utc, identity
            )
            analysis_run_id = uuid4()
            cursor.execute(
                "INSERT INTO analysis.technical_analysis_runs "
                "(analysis_run_id, symbol_id, data_cutoff_utc, analyzed_at_utc, "
                "algorithm_version_id, "
                "parameters_hash, source_snapshot_id, state) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s, %s)",
                (
                    analysis_run_id,
                    symbol_id,
                    data_cutoff_utc,
                    analyzed_at,
                    version_id,
                    parameters_hash,
                    snapshot_id,
                    AnalysisState.CONFIRMED.value,
                ),
            )
            _insert_structures(cursor, analysis_run_id, analysis)
            _insert_break_and_poi(cursor, analysis_run_id, analysis)
            _insert_consolidations(cursor, analysis_run_id, analysis)
            _insert_levels_and_targets(cursor, analysis_run_id, analysis)
            _insert_explanations(cursor, analysis_run_id, analysis.explanation)
        return PersistedTechnicalAnalysis(analysis_run_id, snapshot_id, analyzed_at)

    # Captura las velas actuales antes del análisis para que el motor use exactamente ese snapshot.
    def capture_snapshot(
        self, identity: InstrumentIdentity, data_cutoff_utc: datetime
    ) -> UUID:
        psycopg = _psycopg()
        with psycopg.connect(self._database_url) as connection, connection.cursor() as cursor:
            return _insert_snapshot(cursor, _symbol_id(cursor, identity), data_cutoff_utc, identity)

    # Lee un resumen de una ejecución para comprobar sus resultados sin modificarla.
    def verification_report(self, analysis_run_id: UUID) -> dict[str, object]:
        psycopg = _psycopg()
        with psycopg.connect(self._database_url) as connection, connection.cursor() as cursor:
            run = cursor.execute(
                "SELECT state, data_cutoff_utc, analyzed_at_utc, source_snapshot_id "
                "FROM analysis.technical_analysis_runs "
                "WHERE analysis_run_id = %s",
                (analysis_run_id,),
            ).fetchone()
            if run is None:
                raise ConfigurationError("No existe la ejecución técnica solicitada")
            snapshot = cursor.execute(
                "SELECT content_hash, fingerprint_version FROM analysis.source_snapshots "
                "WHERE source_snapshot_id = %s",
                (run[3],),
            ).fetchone()
            snapshot_bar_count = cursor.execute(
                "SELECT COUNT(*) FROM analysis.snapshot_bars WHERE source_snapshot_id = %s",
                (run[3],),
            ).fetchone()[0]
            counts = {
                "structures": _count_for_run(
                    cursor, "technical.market_structures", analysis_run_id
                ),
                "structural_breaks": _count_for_run(
                    cursor, "technical.structural_breaks", analysis_run_id
                ),
                "points_of_interest": _count_for_run(
                    cursor, "technical.points_of_interest", analysis_run_id
                ),
                "consolidations": _count_for_run(
                    cursor, "technical.consolidations", analysis_run_id
                ),
                "levels": _count_for_run(cursor, "technical.technical_levels", analysis_run_id),
                "targets": _count_for_run(cursor, "technical.structural_targets", analysis_run_id),
                "explanations": _count_for_run(
                    cursor, "analysis.technical_explanations", analysis_run_id
                ),
            }
        return {
            "analysis_run_id": str(analysis_run_id),
            "state": run[0],
            "data_cutoff_utc": run[1].isoformat(),
            "analyzed_at_utc": run[2].isoformat(),
            "source_snapshot": {
                "source_snapshot_id": str(run[3]),
                "content_hash": snapshot[0] if snapshot else None,
                "fingerprint_version": snapshot[1] if snapshot else None,
                "bar_count": snapshot_bar_count,
            },
            "result_counts": counts,
        }


# Resuelve el símbolo por fuente para impedir mezclar instrumentos de brókeres distintos.
def _symbol_id(cursor: object, identity: InstrumentIdentity) -> UUID:
    row = cursor.execute(
        "SELECT symbol.symbol_id FROM market.symbols symbol "
        "JOIN market.data_sources source ON source.data_source_id = symbol.data_source_id "
        "WHERE source.name = %s AND source.broker = %s AND source.server = %s "
        "AND symbol.broker_symbol = %s",
        (identity.source_name, identity.broker, identity.server, identity.symbol),
    ).fetchone()
    if row is None:
        raise ConfigurationError("No existe el símbolo importado para guardar el análisis")
    return row[0]


# Cuenta resultados usando nombres internos controlados por el código.
def _count_for_run(cursor: object, table: str, analysis_run_id: UUID) -> int:
    return cursor.execute(
        f"SELECT COUNT(*) FROM {table} WHERE analysis_run_id = %s", (analysis_run_id,)
    ).fetchone()[0]


# Recupera o registra la versión exacta de reglas que produjo el análisis.
def _algorithm_version_id(
    cursor: object, name: str, version: str, source_revision: str
) -> UUID:
    row = cursor.execute(
        "SELECT algorithm_version_id FROM system.algorithm_versions "
        "WHERE algorithm_name = %s AND version = %s",
        (name, version),
    ).fetchone()
    if row is not None:
        return row[0]
    identifier = uuid4()
    cursor.execute(
        "INSERT INTO system.algorithm_versions "
        "(algorithm_version_id, algorithm_name, version, source_revision) VALUES (%s, %s, %s, %s)",
        (identifier, name, version, source_revision),
    )
    return identifier


# Identifica el código con commit Git o huella reproducible cuando no existe repositorio Git.
def code_revision() -> str:
    configured = os.environ.get("XAU_CODE_REVISION")
    if configured:
        return configured
    root = Path(__file__).resolve().parents[3]
    try:
        commit = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=root,
            capture_output=True,
            check=True,
            text=True,
            timeout=3,
        ).stdout.strip()
    except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired):
        commit = ""
    if commit:
        return f"git:{commit}"
    digest = hashlib.sha256()
    for source in sorted((root / "src" / "xau_collector").rglob("*.py")):
        digest.update(source.relative_to(root).as_posix().encode())
        digest.update(source.read_bytes())
    return f"source-sha256:{digest.hexdigest()}"


# Calcula una huella estable de los parámetros para detectar cambios de reglas.
def _parameters_hash(parameters: dict[str, object]) -> str:
    payload = json.dumps(parameters, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode()).hexdigest()


# Persiste parámetros una sola vez por hash, conservando el JSON que se aplicó.
def _ensure_parameters(cursor: object, parameter_hash: str, parameters: dict[str, object]) -> None:
    cursor.execute(
        "INSERT INTO system.analysis_parameters (parameters_hash, parameters_json) VALUES (%s, %s) "
        "ON CONFLICT (parameters_hash) DO NOTHING",
        (parameter_hash, json.dumps(parameters, sort_keys=True)),
    )


# Crea un snapshot determinista de las velas exactas usadas por el análisis.
def _insert_snapshot(
    cursor: object, symbol_id: UUID, cutoff_utc: datetime, identity: InstrumentIdentity
) -> UUID:
    snapshot_bars = _snapshot_bars(cursor, symbol_id, cutoff_utc)
    bar_counts = {
        timeframe: sum(1 for bar in snapshot_bars if bar[1] == timeframe)
        for timeframe in ("H4", "H1", "M15", "M5")
    }
    content_hash = snapshot_content_hash(snapshot_bars)
    row = cursor.execute(
        "SELECT source_snapshot_id FROM analysis.source_snapshots "
        "WHERE symbol_id = %s AND data_cutoff_utc = %s AND content_hash = %s",
        (symbol_id, cutoff_utc, content_hash),
    ).fetchone()
    if row is not None:
        return row[0]
    identifier = uuid4()
    cursor.execute(
        "INSERT INTO analysis.source_snapshots "
        "(source_snapshot_id, symbol_id, data_cutoff_utc, source_reference, bar_counts, "
        "content_hash, created_at_utc, fingerprint_version) "
        "VALUES (%s, %s, %s, %s, %s, %s, %s, %s)",
        (
            identifier,
            symbol_id,
            cutoff_utc,
            f"postgres:{identity.source_name}:{identity.server}:{identity.symbol}",
            json.dumps(bar_counts, sort_keys=True),
            content_hash,
            datetime.now(UTC),
            2,
        ),
    )
    for ordinal, bar in enumerate(snapshot_bars, start=1):
        cursor.execute(
            "INSERT INTO analysis.snapshot_bars "
            "(source_snapshot_id, timeframe, ordinal, market_bar_id, open_time_utc, "
            "close_time_utc, "
            "open, high, low, close, tick_volume, real_volume, spread_points, revision) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
            (identifier, bar[1], ordinal, *bar[0:1], *bar[2:]),
        )
    return identifier


# Calcula una huella estable del contenido exacto de las velas utilizadas por un análisis.
def snapshot_content_hash(snapshot_bars: tuple[tuple[object, ...], ...]) -> str:
    fingerprint = [
        {
            "timeframe": bar[1],
            "market_bar_id": str(bar[0]),
            "open_time_utc": bar[2].isoformat(),
            "close_time_utc": bar[3].isoformat(),
            "open": str(bar[4]),
            "high": str(bar[5]),
            "low": str(bar[6]),
            "close": str(bar[7]),
            "tick_volume": bar[8],
            "real_volume": bar[9],
            "spread_points": bar[10],
            "revision": bar[11],
        }
        for bar in snapshot_bars
    ]
    serialized = json.dumps(fingerprint, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(serialized.encode()).hexdigest()


# Recupera las ventanas exactas que cada cálculo multitemporal consulta en PostgreSQL.
def _snapshot_bars(
    cursor: object, symbol_id: UUID, cutoff_utc: datetime
) -> tuple[tuple[object, ...], ...]:
    results: list[tuple[object, ...]] = []
    for timeframe, limit in (("H4", 180), ("H1", 360), ("M15", 480), ("M5", None)):
        suffix = (
            " ORDER BY open_time_utc"
            if limit is None
            else " ORDER BY open_time_utc DESC LIMIT %s"
        )
        query = (
            "SELECT market_bar_id, timeframe, open_time_utc, close_time_utc, open, high, low, "
            "close, tick_volume, real_volume, spread_points, revision "
            "FROM market.market_bars WHERE symbol_id = %s AND timeframe = %s "
            "AND is_current AND close_time_utc <= %s" + suffix
        )
        params: tuple[object, ...] = (
            (symbol_id, timeframe, cutoff_utc)
            if limit is None
            else (symbol_id, timeframe, cutoff_utc, limit)
        )
        rows = cursor.execute(query, params).fetchall()
        results.extend(rows if limit is None else reversed(rows))
    return tuple(results)


# Inserta estructura por temporalidad con sus métricas auditables.
def _insert_structures(
    cursor: object, analysis_run_id: UUID, analysis: HistoricalMultiTimeframeAnalysis
) -> None:
    for run in (analysis.h4, analysis.h1, analysis.m15, analysis.m5):
        summary = {
            "swing_high_count": run.swing_high_count,
            "swing_low_count": run.swing_low_count,
            "buy_side_liquidity_count": run.buy_side_liquidity_count,
            "sell_side_liquidity_count": run.sell_side_liquidity_count,
            "consolidation_count": run.consolidation_count,
            "coverage_state": run.coverage_state,
            "coverage_gap_count": run.coverage_gap_count,
        }
        cursor.execute(
            "INSERT INTO technical.market_structures "
            "(market_structure_id, analysis_run_id, timeframe, direction, bar_count, "
            "window_high, window_low, summary) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s, %s)",
            (
                uuid4(), analysis_run_id, run.timeframe, run.direction, run.bar_count,
                run.window_high, run.window_low, json.dumps(summary, sort_keys=True),
            ),
        )


# Persiste los BOS calculados por cada temporalidad y el POI candidato específico de H1.
def _insert_break_and_poi(
    cursor: object, analysis_run_id: UUID, analysis: HistoricalMultiTimeframeAnalysis
) -> None:
    h1 = analysis.h1
    for run in (analysis.h4, h1, analysis.m15, analysis.m5):
        if run.latest_body_break_direction is None:
            continue
        cursor.execute(
            "INSERT INTO technical.structural_breaks "
            "(structural_break_id, analysis_run_id, timeframe, event_type, direction, details) "
            "VALUES (%s, %s, %s, %s, %s, %s)",
            (
                uuid4(),
                analysis_run_id,
                run.timeframe,
                "BOS",
                run.latest_body_break_direction,
                json.dumps(
                    {
                        "candidate_poi_range": run.candidate_poi_range,
                        "confirmed_at_utc": _iso_or_none(run.latest_body_break_at_utc),
                        "window_high": run.window_high,
                        "window_low": run.window_low,
                    },
                    sort_keys=True,
                ),
            ),
        )
    if h1.candidate_poi_range is not None:
        low, high = h1.candidate_poi_range
        cursor.execute(
            "INSERT INTO technical.points_of_interest "
            "(point_of_interest_id, analysis_run_id, timeframe, low, high, state, details) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s)",
            (
                uuid4(), analysis_run_id, "H1", low, high, analysis.confirmation.m15_state,
                json.dumps({"confirmation": asdict(analysis.confirmation)}),
            ),
        )
    _insert_confirmation_events(cursor, analysis_run_id, analysis)


# Persiste únicamente confirmaciones que el motor realmente calculó en M15 y M5.
def _insert_confirmation_events(
    cursor: object, analysis_run_id: UUID, analysis: HistoricalMultiTimeframeAnalysis
) -> None:
    confirmation = analysis.confirmation
    if confirmation.m15_state in ("CONFIRMADO", "INVALIDADO"):
        cursor.execute(
            "INSERT INTO technical.structural_breaks "
            "(structural_break_id, analysis_run_id, timeframe, event_type, direction, details) "
            "VALUES (%s, %s, %s, %s, %s, %s)",
            (
                uuid4(),
                analysis_run_id,
                "M15",
                "CONFIRMACION_POI",
                confirmation.poi_direction or "SIN_DIRECCION",
                json.dumps(
                    {
                        "state": confirmation.m15_state,
                        "confirmed_at_utc": _iso_or_none(confirmation.m15_confirmed_at_utc),
                    }
                ),
            ),
        )
    for event_type, detected, detected_at in (
        ("BARRIDO", confirmation.m5_sweep, confirmation.m5_sweep_at_utc),
        ("REACCION", confirmation.m5_reaction, confirmation.m5_reaction_at_utc),
        ("RUPTURA_CUERPO", confirmation.m5_body_break, confirmation.m5_body_break_at_utc),
    ):
        if detected:
            cursor.execute(
                "INSERT INTO technical.structural_breaks "
                "(structural_break_id, analysis_run_id, timeframe, event_type, direction, details) "
                "VALUES (%s, %s, %s, %s, %s, %s)",
                (
                    uuid4(),
                    analysis_run_id,
                    "M5",
                    event_type,
                    confirmation.poi_direction or "SIN_DIRECCION",
                    json.dumps({"detected_at_utc": _iso_or_none(detected_at)}),
                ),
            )


# Convierte una fecha opcional en evidencia JSON sin introducir formatos locales ambiguos.
def _iso_or_none(value: datetime | None) -> str | None:
    return value.isoformat() if value is not None else None


# Inserta niveles y objetivos como resultados de esta ejecución concreta.
def _insert_levels_and_targets(
    cursor: object, analysis_run_id: UUID, analysis: HistoricalMultiTimeframeAnalysis
) -> None:
    for level in analysis.key_levels:
        cursor.execute(
            "INSERT INTO technical.technical_levels "
            "(technical_level_id, analysis_run_id, period, high, low) VALUES (%s, %s, %s, %s, %s)",
            (uuid4(), analysis_run_id, level.period, level.high, level.low),
        )
    for direction, targets in (
        ("ALCISTA", analysis.targets_above),
        ("BAJISTA", analysis.targets_below),
    ):
        for ordinal, price in enumerate(targets, start=1):
            cursor.execute(
                "INSERT INTO technical.structural_targets "
                "(structural_target_id, analysis_run_id, direction, ordinal, price) "
                "VALUES (%s, %s, %s, %s, %s)",
                (uuid4(), analysis_run_id, direction, ordinal, price),
            )


# Persiste las zonas de negociación detectadas con su ruptura confirmada.
def _insert_consolidations(
    cursor: object, analysis_run_id: UUID, analysis: HistoricalMultiTimeframeAnalysis
) -> None:
    for timeframe, poi in analysis.consolidations:
        cursor.execute(
            "INSERT INTO technical.consolidations "
            "(consolidation_id, analysis_run_id, timeframe, starts_at_utc, ends_at_utc, low, high, "
            "breakout_direction, breakout_at_utc, state, evidence) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
            (
                uuid4(), analysis_run_id, timeframe, poi.first_open_utc, poi.last_open_utc,
                poi.low, poi.high, poi.breakout_direction, poi.breakout_open_utc, "CONFIRMADO",
                json.dumps({"detector": "consolidation_poi"}),
            ),
        )
# Conserva la explicación ordenada para que futuras interfaces no tengan que reconstruirla.
def _insert_explanations(
    cursor: object, analysis_run_id: UUID, explanation: tuple[str, ...]
) -> None:
    for order, content in enumerate(explanation, start=1):
        cursor.execute(
            "INSERT INTO analysis.technical_explanations "
            "(technical_explanation_id, analysis_run_id, explanation_order, content) "
            "VALUES (%s, %s, %s, %s)",
            (uuid4(), analysis_run_id, order, content),
        )


# Carga psycopg solo para persistencia PostgreSQL, manteniendo disponibles los flujos CSV locales.
def _psycopg() -> object:
    try:
        import psycopg
    except ImportError as exc:
        raise DependencyUnavailableError("Instale la dependencia opcional postgres") from exc
    return psycopg
