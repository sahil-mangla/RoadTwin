import { useEffect, useState } from "react";
import { getMyNotifications, markNotificationRead } from "../api/intel";
import type { CitizenNotification } from "../intelTypes";

const POLL_MS = 30_000;

/** RPWF-02: in-app updates on the citizen's own reports (by device cookie). */
export function NotificationsPanel() {
  const [items, setItems] = useState<CitizenNotification[]>([]);

  useEffect(() => {
    let cancelled = false;
    const load = () =>
      getMyNotifications()
        .then((n) => !cancelled && setItems(n))
        .catch(() => undefined); // non-critical: never block the report form
    load();
    const timer = setInterval(load, POLL_MS);
    return () => {
      cancelled = true;
      clearInterval(timer);
    };
  }, []);

  if (items.length === 0) return null;
  const unread = items.filter((n) => !n.read).length;

  async function dismiss(id: string) {
    await markNotificationRead(id).catch(() => undefined);
    setItems((prev) => prev.map((n) => (n.id === id ? { ...n, read: true } : n)));
  }

  return (
    <div className="notifications">
      <h3>Updates on your reports {unread > 0 && <span className="status-badge">{unread} new</span>}</h3>
      <ul>
        {items.map((n) => (
          <li key={n.id} className={n.read ? "read" : ""}>
            <span>{n.message}</span> <span className="muted small">{new Date(n.created_at).toLocaleString()}</span>
            {!n.read && (
              <button type="button" className="link" onClick={() => dismiss(n.id)}>Mark read</button>
            )}
          </li>
        ))}
      </ul>
    </div>
  );
}
