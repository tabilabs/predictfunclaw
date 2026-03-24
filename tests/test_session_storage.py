from __future__ import annotations

from lib.session_storage import FundAndActionSessionRecord, SessionStorage


def test_session_storage_round_trips_and_picks_latest_active_record(tmp_path) -> None:
    storage = SessionStorage(tmp_path)
    storage.upsert(
        FundAndActionSessionRecord(
            session_id="session-1",
            predict_account_address="0x1234567890123456789012345678901234567890",
            market_id="123",
            position_id="pos-123-yes",
            outcome="YES",
            order_hash=None,
            session_scope="specific-trade",
            funding_plan={"evaluatedAt": "2026-03-24T00:00:00Z"},
            funding_session={"sessionId": "session-1", "status": "pendingFunding"},
            funding_next_step={"task": {"kind": "submitFunding"}},
            created_at="2026-03-24T00:00:00Z",
            updated_at="2026-03-24T00:00:00Z",
        )
    )
    storage.upsert(
        FundAndActionSessionRecord(
            session_id="session-2",
            predict_account_address="0x1234567890123456789012345678901234567890",
            market_id="456",
            position_id="pos-456-no",
            outcome="NO",
            order_hash="0xabc",
            session_scope="specific-trade",
            funding_plan={"evaluatedAt": "2026-03-24T01:00:00Z"},
            funding_session={"sessionId": "session-2", "status": "pendingFollowUp"},
            funding_next_step={"task": {"kind": "submitFollowUp"}},
            created_at="2026-03-24T01:00:00Z",
            updated_at="2026-03-24T01:00:00Z",
        )
    )

    active = storage.get_active_session(
        predict_account_address="0x1234567890123456789012345678901234567890"
    )

    assert active is not None
    assert active.session_id == "session-2"
    assert active.position_id == "pos-456-no"
    assert active.order_hash == "0xabc"
