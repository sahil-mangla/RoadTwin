import { useEffect, useState } from "react";
import { NotificationsPanel } from "./components/NotificationsPanel";
import { AuthorityPage } from "./pages/AuthorityPage";
import { PublicMapPage } from "./pages/PublicMapPage";
import { ReportSubmitPage } from "./pages/ReportSubmitPage";
import { SkeletonPage } from "./pages/SkeletonPage";

// A tiny hash router: four pages with shareable URLs (#/map, #/authority)
// does not yet justify a routing dependency.
const PAGES = {
  report: "Report damage",
  map: "Road health map",
  authority: "Authority dashboard",
  diagnostic: "Internal diagnostic",
} as const;
type Page = keyof typeof PAGES;

function currentPage(): Page {
  const key = window.location.hash.replace(/^#\/?/, "");
  return key in PAGES ? (key as Page) : "report";
}

function App() {
  const [page, setPage] = useState<Page>(currentPage);

  useEffect(() => {
    const onHash = () => setPage(currentPage());
    window.addEventListener("hashchange", onHash);
    return () => window.removeEventListener("hashchange", onHash);
  }, []);

  return (
    <div className={`page-container ${page === "report" ? "" : "wide"}`}>
      <header>
        <h1>RoadTwin</h1>
        <p>
          Citizens report road damage; RoadTwin fuses those reports over time into
          per-road health profiles and a ranked maintenance queue.
        </p>
      </header>
      <nav className="main-nav">
        {(Object.keys(PAGES) as Page[]).map((key) => (
          <a key={key} href={`#/${key}`} className={page === key ? "active" : ""}>
            {PAGES[key]}
          </a>
        ))}
      </nav>
      {page === "report" && (
        <>
          <NotificationsPanel />
          <ReportSubmitPage />
        </>
      )}
      {page === "map" && <PublicMapPage />}
      {page === "authority" && <AuthorityPage />}
      {page === "diagnostic" && <SkeletonPage />}
    </div>
  );
}

export default App;
