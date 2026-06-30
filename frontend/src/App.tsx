import { Toaster } from "@/components/ui/toaster";
import { Toaster as Sonner } from "@/components/ui/sonner";
import { TooltipProvider } from "@/components/ui/tooltip";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { BrowserRouter, Routes, Route } from "react-router-dom";
import { AuthProvider } from "@/contexts/AuthContext";
import ProtectedRoute from "@/components/auth/ProtectedRoute";
import MainApp from "./pages/MainApp";
import Login from "./pages/Login";
import ApiTest from "./pages/ApiTest";
import Lab from "./pages/Lab";
import NotFound from "./pages/NotFound";

const queryClient = new QueryClient();

const App = () => (
  <QueryClientProvider client={queryClient}>
    <TooltipProvider>
      <Toaster />
      <Sonner />
      <BrowserRouter>
        <AuthProvider>
          <Routes>
            {/* 根路由直接进上传/工作区界面，不再展示落地页 */}
            <Route path="/" element={<MainApp />} />
            <Route path="/login" element={<Login />} />
            <Route path="/app" element={
              <ProtectedRoute>
                <MainApp />
              </ProtectedRoute>
            } />
            <Route path="/api-test" element={<ApiTest />} />
            <Route path="/lab" element={<Lab />} />
            {/* ADD ALL CUSTOM ROUTES ABOVE THE CATCH-ALL "*" ROUTE */}
            <Route path="*" element={<NotFound />} />
          </Routes>
        </AuthProvider>
      </BrowserRouter>
    </TooltipProvider>
  </QueryClientProvider>
);

export default App;
