"""
alert_state.py — Local alert deduplication and state persistence.

Writes to data/.alert_state.json. Each alert is keyed by (trade_date, alert_type)
to prevent repeated notifications for the same event on the same trading day.

No external services, no credentials. Dashboard reads this file to show warnings.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Optional


ALERT_STATE_FILE = Path(__file__).parent.parent.parent / "data" / ".alert_state.json"

ALERT_TYPES = {
    "MISSED_RUN",
    "STALE_DATA",
    "PARTIAL_MARKET",
    "PROVIDER_FAILURE",
    "BACKUP_FAILURE",
    "SHADOW_FAILED",
    "DECISION_HASH_CONFLICT",
}


@dataclass
class Alert:
    trade_date: str          # ISO date string
    alert_type: str
    message: str
    first_seen: str          # ISO datetime UTC
    last_seen: str           # ISO datetime UTC
    count: int = 1
    resolved: bool = False

    def key(self) -> str:
        return f"{self.trade_date}:{self.alert_type}"

    def to_dict(self) -> dict:
        return {
            "trade_date": self.trade_date,
            "alert_type": self.alert_type,
            "message": self.message,
            "first_seen": self.first_seen,
            "last_seen": self.last_seen,
            "count": self.count,
            "resolved": self.resolved,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "Alert":
        return cls(
            trade_date=d["trade_date"],
            alert_type=d["alert_type"],
            message=d["message"],
            first_seen=d["first_seen"],
            last_seen=d["last_seen"],
            count=d.get("count", 1),
            resolved=d.get("resolved", False),
        )


class AlertStateManager:
    """Load, record, and query local alert state with deduplication."""

    def __init__(self, state_file: Path = ALERT_STATE_FILE) -> None:
        self._file = state_file
        self._alerts: dict[str, Alert] = {}
        self._load()

    def _load(self) -> None:
        if self._file.exists():
            try:
                data = json.loads(self._file.read_text())
                for entry in data.get("alerts", []):
                    a = Alert.from_dict(entry)
                    self._alerts[a.key()] = a
            except Exception:
                pass

    def _save(self) -> None:
        self._file.parent.mkdir(parents=True, exist_ok=True)
        payload = {"alerts": [a.to_dict() for a in sorted(
            self._alerts.values(),
            key=lambda x: (x.trade_date, x.alert_type),
            reverse=True,
        )]}
        self._file.write_text(json.dumps(payload, indent=2))

    def record(
        self,
        trade_date: date | str,
        alert_type: str,
        message: str,
    ) -> bool:
        """
        Record an alert. Returns True if this is a NEW alert (first occurrence),
        False if it was already recorded (deduplicated).
        """
        trade_date_str = str(trade_date)
        now_iso = datetime.now(timezone.utc).isoformat()
        key = f"{trade_date_str}:{alert_type}"

        if key in self._alerts and not self._alerts[key].resolved:
            self._alerts[key].last_seen = now_iso
            self._alerts[key].count += 1
            self._save()
            return False  # duplicate — already alerted

        self._alerts[key] = Alert(
            trade_date=trade_date_str,
            alert_type=alert_type,
            message=message,
            first_seen=now_iso,
            last_seen=now_iso,
        )
        self._save()
        return True  # new alert

    def resolve(self, trade_date: date | str, alert_type: str) -> None:
        key = f"{trade_date}:{alert_type}"
        if key in self._alerts:
            self._alerts[key].resolved = True
            self._save()

    def active_alerts(self, trade_date: Optional[date | str] = None) -> list[Alert]:
        """Return unresolved alerts, optionally filtered by trade_date."""
        alerts = [a for a in self._alerts.values() if not a.resolved]
        if trade_date is not None:
            alerts = [a for a in alerts if a.trade_date == str(trade_date)]
        return sorted(alerts, key=lambda x: x.first_seen, reverse=True)

    def all_alerts(self, limit: int = 20) -> list[Alert]:
        return sorted(self._alerts.values(), key=lambda x: x.first_seen, reverse=True)[:limit]
