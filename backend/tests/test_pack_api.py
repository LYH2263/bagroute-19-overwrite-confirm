from sqlalchemy import select

from app.models.models import (
    BagItem,
    DeliveryRoute,
    PackBag,
    RejectRecord,
    SubscriberStop,
)


def _make_route(db, max_weight=8.0, max_volume=18.0):
    route = DeliveryRoute(name="测试路线", max_weight_kg=max_weight, max_volume_l=max_volume)
    db.add(route)
    db.flush()
    db.add_all(
        [
            SubscriberStop(route_id=route.id, seq=1, name="甲站", weight_kg=2.0, volume_l=4.0),
            SubscriberStop(route_id=route.id, seq=2, name="乙站", weight_kg=3.5, volume_l=5.5),
            SubscriberStop(route_id=route.id, seq=3, name="大件站", weight_kg=9.5, volume_l=6.0),
        ]
    )
    db.commit()
    return route


def _snapshot(db, route_id):
    bags = db.scalars(
        select(PackBag).where(PackBag.route_id == route_id).order_by(PackBag.bag_index)
    ).all()
    snap = []
    for b in bags:
        items = db.scalars(select(BagItem).where(BagItem.bag_id == b.id)).all()
        snap.append(
            {
                "bag_index": b.bag_index,
                "weight_kg": b.weight_kg,
                "volume_l": b.volume_l,
                "items": [(i.stop_id, i.stop_name) for i in items],
            }
        )
    rejects = db.scalars(select(RejectRecord).where(RejectRecord.route_id == route_id)).all()
    rej = [(r.stop_id, r.stop_name, r.reason) for r in rejects]
    return snap, rej


def test_repack_without_confirm_keeps_old_bags_rejects_and_weights(client, db_session):
    route = _make_route(db_session)
    first = client.post("/api/pack", json={"route_id": route.id})
    assert first.status_code == 200
    old_snap, old_rej = _snapshot(db_session, route.id)
    assert old_snap  # 第一次装袋有结果
    assert old_rej  # 大件站被拒收

    # 收紧限额后，不带确认标记再装 -> 409
    route.max_weight_kg = 1.0
    db_session.commit()
    resp = client.post("/api/pack", json={"route_id": route.id})
    assert resp.status_code == 409

    db_session.expire_all()
    new_snap, new_rej = _snapshot(db_session, route.id)
    assert new_snap == old_snap  # 旧袋明细与袋重保持不变
    assert new_rej == old_rej  # 旧拒收保持不变


def test_repack_with_confirm_uses_new_limits(client, db_session):
    route = _make_route(db_session, max_weight=8.0, max_volume=18.0)
    client.post("/api/pack", json={"route_id": route.id})
    before, _ = _snapshot(db_session, route.id)
    # 初始限额下甲、乙同袋（2.0+3.5<=8）
    assert [len(b["items"]) for b in before] == [2]

    # 收紧重量限额到 4.0，确认覆盖后应拆成两袋
    route.max_weight_kg = 4.0
    db_session.commit()
    blocked = client.post("/api/pack", json={"route_id": route.id})
    assert blocked.status_code == 409

    resp = client.post(
        "/api/pack", json={"route_id": route.id, "confirm_overwrite": True}
    )
    assert resp.status_code == 200
    after, rejects = _snapshot(db_session, route.id)
    assert [len(b["items"]) for b in after] == [1, 1]
    assert [[it[1] for it in b["items"]] for b in after] == [["甲站"], ["乙站"]]
    assert after[0]["weight_kg"] == 2.0
    assert after[1]["weight_kg"] == 3.5
    assert [r[1] for r in rejects] == ["大件站"]


def test_repack_with_confirm_picks_up_new_stop(client, db_session):
    route = _make_route(db_session)
    client.post("/api/pack", json={"route_id": route.id})

    # 新增一个站点
    db_session.add(
        SubscriberStop(route_id=route.id, seq=4, name="丙站", weight_kg=2.0, volume_l=4.0)
    )
    db_session.commit()

    resp = client.post(
        "/api/pack", json={"route_id": route.id, "confirm_overwrite": True}
    )
    assert resp.status_code == 200
    bags = resp.json()
    all_names = [it["stop_name"] for b in bags for it in b["items"]]
    assert "丙站" in all_names


def test_pack_unknown_route_404(client):
    resp = client.post("/api/pack", json={"route_id": 999})
    assert resp.status_code == 404
