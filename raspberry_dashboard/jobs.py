from __future__ import annotations

import os
import sqlite3
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from fastapi import HTTPException
from fastapi.responses import FileResponse


JOBS_DASHBOARD_DIR = Path(
    os.getenv("JOBS_DASHBOARD_DIR", "/opt/job-application-dashboard")
)
JOBS_DB_PATH = Path(
    os.getenv("JOBS_DB_PATH", str(JOBS_DASHBOARD_DIR / "data" / "candidaturas.db"))
)
JOBS_DIST_DIR = Path(
    os.getenv("JOBS_DIST_DIR", str(JOBS_DASHBOARD_DIR / "dist"))
)

ALLOWED_FILTERS = {
    "country": "country",
    "status": "status",
    "work_mode": "work_mode",
    "difficulty": "difficulty",
}
WRITABLE_FIELDS = {
    "status",
    "difficulty",
    "notes",
    "priority",
    "resume_path",
    "resume_version",
    "apply_method",
    "applied_at",
}


def connect() -> sqlite3.Connection:
    if not JOBS_DB_PATH.is_file():
        raise HTTPException(status_code=503, detail="Banco de candidaturas indisponivel")
    connection = sqlite3.connect(JOBS_DB_PATH, timeout=10)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def rows_as_dicts(rows: list[sqlite3.Row]) -> list[dict[str, Any]]:
    return [dict(row) for row in rows]


def list_jobs(params: Mapping[str, str]) -> list[dict[str, Any]]:
    clauses: list[str] = []
    values: list[Any] = []
    search = (params.get("search") or "").strip()
    if search:
        clauses.append(
            "(company LIKE ? OR title LIKE ? OR target_role LIKE ? OR location LIKE ? OR notes LIKE ?)"
        )
        term = f"%{search}%"
        values.extend([term] * 5)

    for query_name, column in ALLOWED_FILTERS.items():
        value = params.get(query_name)
        if value:
            clauses.append(f"{column} = ?")
            values.append(value)

    try:
        minimum = int(params.get("min_compatibility") or 0)
    except ValueError:
        minimum = 0
    if minimum > 0:
        clauses.append("compatibility >= ?")
        values.append(minimum)

    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    query = f"""
        SELECT * FROM jobs
        {where}
        ORDER BY
          CASE difficulty WHEN 'Facil' THEN 1 WHEN 'Media' THEN 2 WHEN 'Complexa' THEN 3 ELSE 4 END,
          compatibility DESC,
          id DESC
    """
    with connect() as connection:
        return rows_as_dicts(connection.execute(query, values).fetchall())


def dashboard_meta() -> dict[str, Any]:
    with connect() as connection:
        summary = dict(
            connection.execute(
                """
                SELECT
                  COUNT(*) AS total,
                  SUM(CASE WHEN status = 'Enviada' THEN 1 ELSE 0 END) AS sent,
                  SUM(CASE WHEN status IN ('Fila', 'Em curso', 'CV adaptado') THEN 1 ELSE 0 END) AS in_progress,
                  SUM(CASE WHEN status = 'Pendente' THEN 1 ELSE 0 END) AS pending,
                  SUM(CASE WHEN status = 'Descartada' THEN 1 ELSE 0 END) AS discarded,
                  SUM(CASE WHEN country = 'Brasil' AND status = 'Enviada' THEN 1 ELSE 0 END) AS sent_brazil,
                  SUM(CASE WHEN country = 'Portugal' AND status = 'Enviada' THEN 1 ELSE 0 END) AS sent_portugal,
                  MAX(updated_at) AS updated_at
                FROM jobs
                """
            ).fetchone()
        )
        options = {
            field: [
                row["value"]
                for row in connection.execute(
                    f"SELECT DISTINCT {field} AS value FROM jobs WHERE {field} IS NOT NULL ORDER BY {field}"
                ).fetchall()
            ]
            for field in ALLOWED_FILTERS.values()
        }
    return {"summary": summary, "options": options}


def update_job(job_id: int, payload: dict[str, Any]) -> dict[str, Any]:
    entries = [(key, value) for key, value in payload.items() if key in WRITABLE_FIELDS]
    if not entries:
        raise HTTPException(status_code=400, detail="Nenhum campo editavel informado")

    with connect() as connection:
        current = connection.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
        if current is None:
            raise HTTPException(status_code=404, detail="Vaga nao encontrada")

        setters = ", ".join(f"{key} = ?" for key, _ in entries)
        values = [None if value == "" else value for _, value in entries]
        connection.execute(
            f"UPDATE jobs SET {setters}, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            (*values, job_id),
        )
        if payload.get("status") and payload["status"] != current["status"]:
            connection.execute(
                """
                INSERT INTO application_events (job_id, event_type, status, details)
                VALUES (?, 'status_changed', ?, ?)
                """,
                (job_id, payload["status"], payload.get("notes")),
            )
        connection.commit()
        return dict(connection.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone())


def dashboard_file(asset_path: str = "") -> FileResponse:
    dist_dir = JOBS_DIST_DIR.resolve()
    requested = (dist_dir / (asset_path or "index.html")).resolve()
    if not requested.is_relative_to(dist_dir):
        raise HTTPException(status_code=404, detail="Arquivo nao encontrado")
    if not requested.is_file():
        requested = dist_dir / "index.html"
    if not requested.is_file():
        raise HTTPException(status_code=503, detail="Frontend de candidaturas indisponivel")
    return FileResponse(requested)
