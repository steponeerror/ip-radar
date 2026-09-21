import { useCallback, useEffect, useState } from "react";
import Layout from "./Layout";
import LookupView from "./LookupView";

// Admin split + 公开数据源页退役:管理台(/admin)走独立文档,数据源
// 管理只在管理台内 —— 公开壳的 hash 路由只剩 lookup。
export type Page = "lookup";

const pageFromHash = (): Page => "lookup";

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
      <LookupView />
    </Layout>
  );
}
