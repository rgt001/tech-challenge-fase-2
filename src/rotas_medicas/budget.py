"""Teto persistente e transacional; chamadas sem consumo conhecido conservam a reserva."""
from __future__ import annotations
from decimal import Decimal, ROUND_CEILING
from pathlib import Path
import json
import sqlite3
import uuid
from .storage import utc_now,write_json

INPUT_UPPER_PER_MILLION = Decimal("0.125")
INPUT_PER_MILLION = Decimal("0.10")
CACHED_PER_MILLION = Decimal("0.01")
OUTPUT_PER_MILLION = Decimal("0.50")
LIMIT_MICRO_USD = 1_000_000


class BudgetExceeded(RuntimeError):
    pass


def cost_micro(input_tokens: int, output_tokens: int, cached_tokens: int = 0, *, upper=True) -> int:
    if min(input_tokens, output_tokens, cached_tokens) < 0 or cached_tokens > input_tokens:
        raise ValueError("Consumo de tokens inválido")
    price = INPUT_UPPER_PER_MILLION if upper else INPUT_PER_MILLION
    # Um microdólar por token equivale a um dólar por milhão de tokens.
    return int(((input_tokens-cached_tokens)*price + cached_tokens*CACHED_PER_MILLION
                + output_tokens*OUTPUT_PER_MILLION).to_integral_value(rounding=ROUND_CEILING))


class BudgetLedger:
    def __init__(self, path: Path):
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            db.execute("""CREATE TABLE IF NOT EXISTS calls (
                id TEXT PRIMARY KEY, created TEXT NOT NULL, model TEXT NOT NULL,
                state TEXT NOT NULL, reserved INTEGER NOT NULL, charged INTEGER NOT NULL,
                input_tokens INTEGER, output_tokens INTEGER, cached_tokens INTEGER,
                response_id TEXT, note TEXT)""")
            exported=path.parent/"budget-summary.json"
            if exported.is_file():
                # A cópia portável preserva o gasto do projeto ao reconstruir o DB local.
                saved=json.loads(exported.read_text(encoding="utf-8"))
                columns=["id","created","model","state","reserved","charged","input_tokens","output_tokens","cached_tokens","response_id","note"]
                db.execute("BEGIN IMMEDIATE")
                if db.execute("SELECT COUNT(*) FROM calls").fetchone()[0]==0:
                    for row in saved["calls"]:
                        db.execute("INSERT INTO calls VALUES(?,?,?,?,?,?,?,?,?,?,?)",tuple(row.get(k) for k in columns))
                db.commit()

    def connect(self):
        return sqlite3.connect(self.path, timeout=30, isolation_level=None)

    def reserve(self, input_tokens: int, max_output_tokens: int, model="gpt-6-luna") -> str:
        if model != "gpt-6-luna":
            raise ValueError("O orçamento está parametrizado exclusivamente para gpt-6-luna")
        reserved = cost_micro(input_tokens, max_output_tokens)
        identifier = uuid.uuid4().hex
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            total = db.execute("SELECT COALESCE(SUM(charged),0) FROM calls").fetchone()[0]
            if db.execute("SELECT COUNT(*) FROM calls WHERE state='overrun'").fetchone()[0]:
                db.rollback()
                raise BudgetExceeded("Contagem divergente registrada; novas chamadas bloqueadas")
            if total + reserved > LIMIT_MICRO_USD:
                db.rollback()
                raise BudgetExceeded("A reserva ultrapassaria o teto acumulado de US$ 1")
            db.execute("INSERT INTO calls(id,created,model,state,reserved,charged,input_tokens) VALUES(?,?,?,?,?,?,?)",
                       (identifier,utc_now(),model,"reserved",reserved,reserved,input_tokens))
            db.commit()
        self.export()
        return identifier

    def settle(self, identifier, *, input_tokens, output_tokens, cached_tokens=0, response_id=None):
        charged = cost_micro(input_tokens,output_tokens,cached_tokens)
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT reserved,state FROM calls WHERE id=?",(identifier,)).fetchone()
            if row is None or row[1] != "reserved":
                db.rollback()
                raise ValueError("Reserva ausente ou já reconciliada")
            if charged > row[0]:
                # Registra o consumo, mas impede novas chamadas e expõe a divergência.
                note = "Consumo superior à reserva: divergência de contagem ou preço"
                state = "overrun"
            else:
                note, state = None, "settled"
            db.execute("UPDATE calls SET state=?,charged=?,input_tokens=?,output_tokens=?,cached_tokens=?,response_id=?,note=? WHERE id=?",
                       (state,charged,input_tokens,output_tokens,cached_tokens,response_id,note,identifier))
            db.commit()
        self.export()
        if state == "overrun":
            raise RuntimeError(note)

    def mark_unknown(self, identifier, note):
        with self.connect() as db:
            db.execute("UPDATE calls SET state='unknown',note=? WHERE id=? AND state='reserved'",(note,identifier))
        self.export()

    def export(self):
        # O DB transacional é a autoridade durante execução; este snapshot é portável.
        write_json(self.path.parent/"budget-summary.json",self.summary())

    def summary(self):
        with self.connect() as db:
            db.row_factory = sqlite3.Row
            rows = [dict(row) for row in db.execute("SELECT * FROM calls ORDER BY created,id")]
        total = sum(r["charged"] for r in rows)
        return {"limit_usd":1.0,"committed_upper_usd":total/1e6,
                "remaining_usd":max(0,LIMIT_MICRO_USD-total)/1e6,"calls":rows,
                "pricing_source":"https://developers.openai.com/api/docs/models/gpt-6-luna",
                "pricing_checked":"2026-10-09", "accounting":"conservative_upper_bound"}
