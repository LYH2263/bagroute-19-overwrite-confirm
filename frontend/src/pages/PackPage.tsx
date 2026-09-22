import { useEffect, useState } from "react";
import { api } from "../api/client";
type R = { id: number; name: string };
type Bag = { id: number; route_id: number; bag_index: number; weight_kg: number; volume_l: number; items: { stop_name: string }[] };
type Reject = { route_id: number };
export default function PackPage() {
  const [routes, setRoutes] = useState<R[]>([]);
  const [rid, setRid] = useState<number | "">("");
  const [bags, setBags] = useState<Bag[]>([]);
  const [hasResult, setHasResult] = useState(false);
  const [msg, setMsg] = useState(""); const [err, setErr] = useState("");
  useEffect(() => { api<R[]>("/routes").then(r => { setRoutes(r); if (r[0]) setRid(r[0].id); }); }, []);
  useEffect(() => {
    setMsg(""); setErr("");
    if (rid === "") { setBags([]); setHasResult(false); return; }
    Promise.all([api<Bag[]>("/bags"), api<Reject[]>("/rejects")])
      .then(([allBags, allRej]) => {
        setBags(allBags.filter(b => b.route_id === rid));
        setHasResult(allBags.some(b => b.route_id === rid) || allRej.some(r => r.route_id === rid));
      })
      .catch(() => { setBags([]); setHasResult(false); });
  }, [rid]);
  async function run() {
    setMsg(""); setErr("");
    let confirmOverwrite = false;
    if (hasResult) {
      if (!window.confirm("该路线已有装袋结果，重新装袋将覆盖现有袋明细、拒收记录和袋重。确认覆盖？")) {
        setErr("未确认覆盖，已保留原装袋结果");
        return;
      }
      confirmOverwrite = true;
    }
    try {
      const out = await api<Bag[]>("/pack", { method: "POST", body: JSON.stringify({ route_id: rid, confirm_overwrite: confirmOverwrite }) });
      setBags(out);
      setHasResult(true);
      setMsg(`完成装袋：${out.length} 袋`);
    } catch (e) { setErr(e instanceof Error ? e.message : String(e)); }
  }
  return (<>
    <h2>装袋</h2>
    <div className="toolbar">
      <select value={rid} onChange={e => setRid(Number(e.target.value))}>{routes.map(r => <option key={r.id} value={r.id}>{r.name}</option>)}</select>
      <button onClick={run}>按路线顺序双约束装袋</button>
    </div>
    {msg && <div className="ok">{msg}</div>}
    {err && <div className="err">{err}</div>}
    {bags.map(b => (
      <div key={b.id}>
        <div className="mono">袋 {b.bag_index} · {b.weight_kg}kg / {b.volume_l}L</div>
        <div className="bag-row">{b.items.map((it, i) => <div className="bag-block" key={i}>{it.stop_name}</div>)}</div>
      </div>
    ))}
  </>);
}
