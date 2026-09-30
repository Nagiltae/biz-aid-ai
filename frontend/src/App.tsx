import { Navigate, Route, Routes } from "react-router-dom";
import { AiSearchPage } from "./features/ai/AiSearchPage";
import { LoginPage } from "./features/auth/LoginPage";
import { RequireAuth } from "./features/auth/RequireAuth";
import { CompanyPage } from "./features/company/CompanyPage";
import { ProgramDetailPage } from "./features/programs/ProgramDetailPage";
import { ProgramListPage } from "./features/programs/ProgramListPage";
import { Layout } from "./shared/components/Layout";

// 지원사업 목록·상세는 공개 공고라 로그인 없이 볼 수 있고, 기업정보·AI 검색은 로그인이 필요하다(Spring 보안 규칙과 같다).
export function App() {
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route element={<Layout />}>
        <Route path="/" element={<Navigate to="/ai" replace />} />
        <Route path="/ai" element={<RequireAuth><AiSearchPage /></RequireAuth>} />
        <Route path="/programs" element={<ProgramListPage />} />
        <Route path="/programs/:pblancId" element={<ProgramDetailPage />} />
        <Route path="/company" element={<RequireAuth><CompanyPage /></RequireAuth>} />
        <Route path="*" element={<Navigate to="/ai" replace />} />
      </Route>
    </Routes>
  );
}
