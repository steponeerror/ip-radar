import { useState, useEffect } from "react";
import { Routes, Route } from "react-router-dom";
import Layout from "./Layout";
import LookupView from "./LookupView";
import SourcesPage from "./pages/SourcesPage";
import { getPublicDemo } from "./api";

export default function App() {
  const [demo, setDemo] = useState(false);
  useEffect(() => {
    getPublicDemo().then(setDemo);
  }, []);
  return (
    <Routes>
      <Route element={<Layout />}>
        <Route index element={<LookupView />} />
        {!demo && <Route path="sources" element={<SourcesPage />} />}
      </Route>
    </Routes>
  );
}
