import { useCallback, useEffect, useState } from "react";
import Layout from "./Layout";
import LookupView from "./LookupView";
import SourcesPage from "./pages/SourcesPage";
import { getPublicDemo } from "./api";

export type Page = "lookup" | "sources";

const pageFromHash = (): Page =>
  location.hash === "#/sources" ? "sources" : "lookup";

export default function App() {
  const [demo, setDemo] = useState(false);
  useEffect(() => {
    getPublicDemo().then(setDemo);
  }, []);
  const [page, setPage] = useState<Page>(pageFromHash);

  useEffect(() => {
    const onHash = () => setPage(pageFromHash());
    window.addEventListener("hashchange", onHash);
    return () => window.removeEventListener("hashchange", onHash);
  }, []);

  // 单一事实源:导航只写 hash,状态由 hashchange 驱动(刷新/手输 URL 同路径)
  const navigate = useCallback((p: Page) => {
    location.hash = p === "sources" ? "#/sources" : "";
  }, []);

  return (
    <Layout page={page} onNavigate={navigate}>
      {page === "sources" && !demo ? <SourcesPage /> : <LookupView />}
    </Layout>
  );
}
