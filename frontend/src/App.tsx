import { Routes, Route, Navigate } from "react-router-dom";
import AppLayout from "./layouts/AppLayout";
import BacktestPage from "./pages/BacktestPage";
import ThetaPlaysPage from "./pages/ThetaPlaysPage";
export default function App() {
  return (
    <Routes>
      <Route element={<AppLayout />}>
        <Route path="/" element={<BacktestPage />} />
        <Route path="/theta-plays" element={<ThetaPlaysPage />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Route>
    </Routes>
  );
}
