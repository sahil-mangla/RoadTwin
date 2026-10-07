import { useState } from "react";
import { ReportSubmitPage } from "./pages/ReportSubmitPage";
import { SkeletonPage } from "./pages/SkeletonPage";

// A plain useState page switch, not a router: the app has exactly two
// pages with no deep-linking, nested-route or URL-state requirement, so
// react-router-dom would be another dependency (and another legitimacy
// check) for no capability this phase needs. A real router becomes
// justified once Phase 7 adds the public map and authority dashboard.
type Page = "report" | "skeleton";

function App() {
  const [page, setPage] = useState<Page>("report");

  return (
    <div className="page-container">
      <header>
        <h1>RoadTwin</h1>
        <p>
          Submit a geotagged photo of road damage below. RoadTwin fuses
          citizen reports over time into per-road-segment health profiles to
          help authorities prioritize maintenance.
        </p>
      </header>
      <nav className="main-nav">
        <button
          type="button"
          className={page === "report" ? "active" : ""}
          onClick={() => setPage("report")}
        >
          Report damage
        </button>
        <button
          type="button"
          className={page === "skeleton" ? "active" : ""}
          onClick={() => setPage("skeleton")}
        >
          Internal diagnostic (skeleton)
        </button>
      </nav>
      {page === "report" ? <ReportSubmitPage /> : <SkeletonPage />}
    </div>
  );
}

export default App;
