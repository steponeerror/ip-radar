import { useCallback, useEffect, useState } from "react";
import Layout from "./Layout";
import LookupView from "./LookupView";
import AdminPage from "./pages/AdminPage";
import SourcesPage from "./pages/SourcesPage";

export type Page = "lookup" | "sources" | "admin";

const pageFromHash = (): Page =>
  location.hash === "#/sources" ? "sources"
    : location.hash === "#/admin" ? "admin"
    : "lookup";

export default function App() {
  const [page, setPage] = useState<Page>(pageFromHash);

  useEffect(() => {
    const onHash = () => setPage(pageFromHash());
    window.addEventListener("hashchange", onHash);
    return () => window.removeEventListener("hashchange", onHash);
  }, []);

  // 单一事实源:导航只写 hash,状态由 hashchange 驱动(刷新/手输 URL 同路径)
  const navigate = useCallback((p: Page) => {
    location.hash = p === "lookup" ? "" : `#/${p}`;
  }, []);

  return (
    <Layout page={page} onNavigate={navigate}>
      {page === "sources" ? <SourcesPage />
        : page === "admin" ? <AdminPage />
        : <LookupView />}
    </Layout>
  );
}
