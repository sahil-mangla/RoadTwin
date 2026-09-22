import { SkeletonPage } from "./pages/SkeletonPage";

function App() {
  return (
    <div className="page-container">
      <header>
        <h1>RoadTwin — Walking Skeleton</h1>
        <p>
          This page is the Phase 1 Walking Skeleton, proving the Report
          data contract is wired end-to-end from browser to Postgres and
          back. It is <strong>not</strong> the citizen reporting UI —
          that ships in a later phase with image upload and a map.
        </p>
      </header>
      <SkeletonPage />
    </div>
  );
}

export default App;
