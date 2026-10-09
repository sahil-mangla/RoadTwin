import { useCallback, useEffect, useState } from "react";
import type { FormEvent } from "react";
import {
  ApiError,
  changeRepairStatus,
  getAuthoritySegment,
  getOverview,
  getQueue,
  login,
  logout,
  updateInputs,
  whoAmI,
} from "../api/intel";
import { BandBadge, BandLegend, HealthMap, OutlookView, ProvisionalNote, Sparkline } from "../components/intel";
import type { AuthoritySegmentDetail, Overview, QueueItem, StaffUser } from "../intelTypes";

const FACTOR_LABELS: Record<string, string> = {
  severity: "Damage severity",
  deterioration: "Deterioration rate",
  density: "Damage density",
  evidence: "Evidence strength",
  traffic: "Traffic exposure",
  importance: "Road importance",
  vulnerable: "Vulnerable locations nearby",
  repair_recency: "Time since repair",
};

const NEXT_STATUSES: Record<string, string[]> = {
  none: ["received", "in_progress", "resolved"],
  received: ["in_progress", "resolved"],
  in_progress: ["resolved", "received"],
  resolved: ["received"],
};

const label = (s: string) => s.replace("_", " ");

/** AUTH-01: staff log in before seeing anything on this page. */
export function AuthorityPage() {
  const [staff, setStaff] = useState<StaffUser | null | undefined>(undefined);

  useEffect(() => {
    whoAmI().then(setStaff).catch(() => setStaff(null));
  }, []);

  if (staff === undefined) return <p>Checking session…</p>;
  if (staff === null) return <LoginForm onLogin={setStaff} />;
  return <Dashboard staff={staff} onLogout={() => logout().finally(() => setStaff(null))} />;
}

function LoginForm({ onLogin }: { onLogin: (s: StaffUser) => void }) {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function submit(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      onLogin(await login(email, password));
    } catch (err) {
      setError(err instanceof ApiError && err.status === 401 ? "Invalid email or password." : (err as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="login">
      <h2>Authority staff sign-in</h2>
      <form onSubmit={submit}>
        <label>Email <input type="email" value={email} onChange={(e) => setEmail(e.target.value)} required autoComplete="username" /></label>
        <label>Password <input type="password" value={password} onChange={(e) => setPassword(e.target.value)} required autoComplete="current-password" /></label>
        <button type="submit" disabled={busy}>{busy ? "Signing in…" : "Sign in"}</button>
        {error && <div className="error-banner">{error}</div>}
      </form>
      <p className="muted small">Accounts are created by an administrator; there is no public sign-up.</p>
    </section>
  );
}

function Dashboard({ staff, onLogout }: { staff: StaffUser; onLogout: () => void }) {
  const [overview, setOverview] = useState<Overview | null>(null);
  const [queue, setQueue] = useState<QueueItem[]>([]);
  const [selected, setSelected] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(() => {
    Promise.all([getOverview(), getQueue()])
      .then(([o, q]) => {
        setOverview(o);
        setQueue(q);
      })
      .catch((e: Error) => setError(e.message));
  }, []);

  useEffect(refresh, [refresh]);

  return (
    <section>
      <div className="dash-header">
        <h2>Authority dashboard</h2>
        <span className="muted small">
          {staff.email} · <button type="button" className="link" onClick={onLogout}>Sign out</button>{" "}
          · <button type="button" className="link" onClick={refresh}>Refresh</button>
        </span>
      </div>
      {error && <div className="error-banner">{error}</div>}
      {overview && (
        <>
          <ProvisionalNote text={overview.note} />
          <div className="cards">
            <Card title="Average health" value={overview.average_health === null ? "–" : overview.average_health.toFixed(0)} sub={`${overview.assessed_segments}/${overview.segments} roads assessed`} />
            <Card title="Critical roads" value={overview.critical_roads} sub="Critical or severely degraded" tone="bad" />
            <Card title="Rapidly deteriorating" value={overview.rapidly_deteriorating} sub="Falling fast" tone="warn" />
            <Card title="Predicted failures" value={overview.predicted_failures} sub="Forecast below 40 within 90 days" tone="warn" />
          </div>
          <p className="muted small">
            Bands: {Object.entries(overview.band_counts).map(([b, n]) => `${b} ${n}`).join(" · ")} · Repairs:{" "}
            {Object.entries(overview.repair_status_counts).map(([s, n]) => `${label(s)} ${n}`).join(" · ") || "none"}
          </p>
        </>
      )}

      <h3>Road health map</h3>
      <BandLegend />
      <HealthMap
        height={360}
        segments={queue.map((q) => ({
          ...q,
          id: q.segment_id,
          label: `#${q.rank} ${q.segment_identifier}`,
          detail: `priority ${q.priority_score.toFixed(0)} (${q.urgency}), health ${q.health_score?.toFixed(0) ?? "–"}, ${q.trend}`,
        }))}
        selectedId={selected}
        onSelect={setSelected}
      />

      <h3>Priority queue</h3>
      {queue.length === 0 ? (
        <p>No ranked roads yet — the queue fills once reports are analysed and assessed.</p>
      ) : (
        <table className="queue">
          <thead>
            <tr><th>#</th><th>Road</th><th>Priority*</th><th>Urgency</th><th>Health*</th><th>Trend</th><th>Repair</th><th>Recommended action</th></tr>
          </thead>
          <tbody>
            {queue.map((q) => (
              <tr key={q.segment_id} className={q.segment_id === selected ? "selected" : ""} onClick={() => setSelected(q.segment_id)}>
                <td>{q.rank}</td>
                <td>{q.road_name ?? q.segment_identifier}</td>
                <td>{q.priority_score.toFixed(0)}</td>
                <td><span className={`urgency ${q.urgency}`}>{q.urgency}</span></td>
                <td><BandBadge band={q.band} score={q.health_score} /></td>
                <td>{q.trend}</td>
                <td>{label(q.repair_status)}</td>
                <td>{q.recommended_action}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      <p className="muted small">* Provisional, tunable scores. Click a row or map segment for its detail and explanation.</p>

      {selected && <SegmentPanel id={selected} onChanged={refresh} />}
    </section>
  );
}

function Card({ title, value, sub, tone }: { title: string; value: string | number; sub: string; tone?: "bad" | "warn" }) {
  return (
    <div className={`card ${tone ?? ""}`}>
      <div className="card-title">{title}</div>
      <div className="card-value">{value}</div>
      <div className="muted small">{sub}</div>
    </div>
  );
}

function SegmentPanel({ id, onChanged }: { id: string; onChanged: () => void }) {
  const [detail, setDetail] = useState<AuthoritySegmentDetail | null>(null);
  const [note, setNote] = useState("");
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(() => {
    getAuthoritySegment(id).then(setDetail).catch((e: Error) => setError(e.message));
  }, [id]);
  useEffect(() => {
    setDetail(null);
    setMessage(null);
    load();
  }, [load]);

  async function move(status: string) {
    setError(null);
    try {
      const r = await changeRepairStatus(id, status, note || null);
      setMessage(`Repair status is now "${r.label}"; ${r.citizens_notified} citizen report(s) notified. Scores refresh within a minute.`);
      setNote("");
      load();
      onChanged();
    } catch (e) {
      setError((e as Error).message);
    }
  }

  async function saveInputs(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const form = new FormData(e.currentTarget);
    const traffic = String(form.get("traffic") ?? "");
    const vulnerable = String(form.get("vulnerable") ?? "");
    try {
      setDetail(
        await updateInputs(id, {
          road_name: String(form.get("road_name") || "") || null,
          road_type: String(form.get("road_type") || "") || null,
          traffic_exposure: traffic === "" ? null : Number(traffic),
          near_vulnerable_location: vulnerable === "" ? null : vulnerable === "yes",
        }),
      );
      setMessage("Inputs saved; the priority score refreshes within a minute.");
      onChanged();
    } catch (err) {
      setError((err as Error).message);
    }
  }

  if (error && !detail) return <div className="error-banner">{error}</div>;
  if (!detail) return <div className="panel"><p>Loading…</p></div>;
  const p = detail.priority;
  const current = detail.health_history[detail.health_history.length - 1];

  return (
    <div className="panel">
      <h3>
        {detail.road_name ?? detail.segment_identifier}{" "}
        {current && <BandBadge band={current.band} score={current.health_score} />}
      </h3>
      <p className="muted small">
        {detail.segment_identifier} · {detail.length_meters?.toFixed(0) ?? "?"} m · repair status{" "}
        <strong>{label(detail.repair_status)}</strong>
        {detail.last_repaired_at && ` · last repaired ${new Date(detail.last_repaired_at).toLocaleDateString()}`}
      </p>
      {message && <div className="confirmation-banner">{message}</div>}
      {error && <div className="error-banner">{error}</div>}

      <h4>Why this priority? (explainability)</h4>
      {p ? (
        <>
          <p><strong>{p.priority_score.toFixed(0)}/100 · {p.urgency}</strong> — {p.recommended_action}</p>
          <p>{p.explanation}</p>
          {p.components && (
            <table className="compact factors">
              <thead><tr><th>Factor</th><th>Value</th><th>Weight</th><th>Points</th></tr></thead>
              <tbody>
                {Object.entries(p.components.factors).map(([k, v]) => (
                  <tr key={k} className={v === null ? "muted" : ""}>
                    <td>{FACTOR_LABELS[k] ?? k}</td>
                    <td>{v === null ? "no data" : v.toFixed(2)}</td>
                    <td>{p.components!.weights[k] === undefined ? "left out" : `${Math.round(p.components!.weights[k] * 100)}%`}</td>
                    <td>
                      <span className="bar" style={{ width: `${(p.components!.contributions[k] ?? 0) * 2}px` }} />{" "}
                      {(p.components!.contributions[k] ?? 0).toFixed(1)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </>
      ) : (
        <p className="muted">Not ranked yet.</p>
      )}

      <div className="two-col">
        <div>
          <h4>Health history</h4>
          <Sparkline points={detail.health_history} />
          <p className="muted small">Dashed line = failure threshold (40).</p>
          <h4>Damage composition</h4>
          {Object.keys(detail.damage_composition).length === 0 ? (
            <p className="muted">No current damage{detail.last_repaired_at ? " since the last repair" : ""}.</p>
          ) : (
            <ul>
              {Object.entries(detail.damage_composition).map(([type, sev]) => (
                <li key={type}>{type}: {Object.entries(sev).map(([s, n]) => `${n} ${s}`).join(", ")}</li>
              ))}
            </ul>
          )}
        </div>
        <div>
          <h4>Forecast</h4>
          <OutlookView outlook={detail.outlook} />
        </div>
      </div>

      <h4>Evidence</h4>
      <table className="compact">
        <thead><tr><th>Seen</th><th>Damage</th><th>Model conf.</th><th>Evidence*</th><th>Counts</th></tr></thead>
        <tbody>
          {detail.evidence.map((e) => (
            <tr key={`${e.report_id}-${e.observed_at}-${e.damage_type}`} title={JSON.stringify(e.evidence_components?.contributions ?? {})}>
              <td>{new Date(e.observed_at).toLocaleDateString()}</td>
              <td>{e.damage_type} ({e.severity})</td>
              <td>{e.confidence === null ? "–" : `${Math.round(e.confidence * 100)}%`}</td>
              <td>{e.verification_score === null ? "–" : e.verification_score.toFixed(2)}</td>
              <td>{e.counts_toward_health ? "yes" : "no (duplicate or pre-repair)"}</td>
            </tr>
          ))}
        </tbody>
      </table>

      <h4>Repair workflow</h4>
      <div className="repair-controls">
        <input placeholder="Note (optional)" value={note} onChange={(e) => setNote(e.target.value)} maxLength={2000} />
        {(NEXT_STATUSES[detail.repair_status] ?? []).map((s) => (
          <button type="button" key={s} onClick={() => move(s)}>Mark {label(s)}</button>
        ))}
      </div>
      {detail.repair_events.length > 0 && (
        <ul className="small">
          {detail.repair_events.map((e) => (
            <li key={e.created_at}>
              {new Date(e.created_at).toLocaleString()}: {label(e.from_status)} → {label(e.to_status)} by {e.staff_email}
              {e.note && ` — ${e.note}`}
            </li>
          ))}
        </ul>
      )}

      <h4>Optional inputs (improve the priority score)</h4>
      <form className="inputs-form" onSubmit={saveInputs} key={detail.segment_id + String(detail.traffic_exposure) + detail.road_type}>
        <label>Road name <input name="road_name" defaultValue={detail.road_name ?? ""} /></label>
        <label>Road type
          <select name="road_type" defaultValue={detail.road_type ?? ""}>
            <option value="">Unknown</option>
            <option value="highway">Highway</option>
            <option value="arterial">Arterial</option>
            <option value="collector">Collector</option>
            <option value="local">Local</option>
          </select>
        </label>
        <label>Traffic exposure (0–1) <input name="traffic" type="number" min="0" max="1" step="0.05" defaultValue={detail.traffic_exposure ?? ""} /></label>
        <label>Near school/hospital
          <select name="vulnerable" defaultValue={detail.near_vulnerable_location === null ? "" : detail.near_vulnerable_location ? "yes" : "no"}>
            <option value="">Unknown</option>
            <option value="yes">Yes</option>
            <option value="no">No</option>
          </select>
        </label>
        <button type="submit">Save inputs</button>
      </form>

      <h4>Reports ({detail.reports.length})</h4>
      <ul className="small">
        {detail.reports.map((r) => (
          <li key={r.id}>
            {new Date(r.observed_at).toLocaleDateString()} · {label(r.status)} · {r.community_upvotes} upvote(s)
            {r.verification_score !== null && ` · evidence ${r.verification_score.toFixed(2)}`}
            {r.is_duplicate && " · duplicate"}
          </li>
        ))}
      </ul>
    </div>
  );
}
