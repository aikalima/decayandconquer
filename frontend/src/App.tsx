import { Routes, Route, Navigate } from "react-router-dom";
import AppLayout from "./layouts/AppLayout";
import BacktestPage from "./pages/BacktestPage";
import ThetaPlaysPage from "./pages/ThetaPlaysPage";
import ChatPage from "./pages/ChatPage";

export default function App() {
  return (
    <Routes>
      <Route element={<AppLayout />}>
        <Route path="/" element={<BacktestPage />} />
        <Route path="/theta-plays" element={<ThetaPlaysPage />} />
        <Route path="/predictions" element={<ChatPage />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Route>
    </Routes>
  );
}
