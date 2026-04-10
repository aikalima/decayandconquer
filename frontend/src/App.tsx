import { Routes, Route, Navigate } from "react-router-dom";
import AppLayout from "./layouts/AppLayout";
import BacktestPage from "./pages/BacktestPage";
import PredictionsPage from "./pages/PredictionsPage";

export default function App() {
  return (
    <Routes>
      <Route element={<AppLayout />}>
        <Route path="/backtest" element={<BacktestPage />} />
        <Route path="/predictions" element={<PredictionsPage />} />
        <Route path="*" element={<Navigate to="/backtest" replace />} />
      </Route>
    </Routes>
  );
}
