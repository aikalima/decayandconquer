import { lazy, Suspense } from "react";
import { Routes, Route, Navigate } from "react-router-dom";
import HomePage from "./pages/HomePage";

const AppLayout = lazy(() => import("./layouts/AppLayout"));
const BacktestPage = lazy(() => import("./pages/BacktestPage"));
const ThetaPlaysPage = lazy(() => import("./pages/ThetaPlaysPage"));
export default function App() {
  return (
    <Suspense fallback={<main role="status" style={{ padding: 32 }}>Loading dashboard...</main>}>
    <Routes>
      <Route path="/" element={<HomePage />} />
      <Route element={<AppLayout />}>
        <Route path="/app/predictions" element={<BacktestPage />} />
        <Route path="/app/theta-plays" element={<ThetaPlaysPage />} />
        <Route path="/theta-plays" element={<Navigate to="/app/theta-plays" replace />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Route>
    </Routes>
    </Suspense>
  );
}
