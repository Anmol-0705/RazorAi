import { BrowserRouter, Routes, Route } from "react-router-dom";
import { RunProvider } from "./context/RunContext";
import Sidebar from "./components/Sidebar";
import TopBar from "./components/TopBar";
import DashboardPage from "./pages/DashboardPage";
import TransactionsPage from "./pages/TransactionsPage";
import ExceptionsPage from "./pages/ExceptionsPage";
import ExceptionDetailPage from "./pages/ExceptionDetailPage";
import ReviewQueuePage from "./pages/ReviewQueuePage";
import EvaluationPage from "./pages/EvaluationPage";

export default function App() {
  return (
    <RunProvider>
      <BrowserRouter>
        <div className="flex h-screen bg-slate-50">
          <Sidebar />
          <div className="flex min-w-0 flex-1 flex-col">
            <TopBar />
            <main className="flex-1 overflow-y-auto p-5">
              <Routes>
                <Route path="/" element={<DashboardPage />} />
                <Route path="/transactions" element={<TransactionsPage />} />
                <Route path="/exceptions" element={<ExceptionsPage />} />
                <Route path="/exceptions/:id" element={<ExceptionDetailPage />} />
                <Route path="/review" element={<ReviewQueuePage />} />
                <Route path="/evaluation" element={<EvaluationPage />} />
              </Routes>
            </main>
          </div>
        </div>
      </BrowserRouter>
    </RunProvider>
  );
}
