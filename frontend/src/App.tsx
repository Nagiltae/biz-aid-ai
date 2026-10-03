import { Navigate, Route, Routes } from "react-router-dom";
import { AiSearchPage } from "./features/ai/AiSearchPage";
import { AccountPage } from "./features/auth/AccountPage";
import { LoginPage } from "./features/auth/LoginPage";
import { RequireAuth } from "./features/auth/RequireAuth";
import { CompanyPage } from "./features/company/CompanyPage";
import { RequireCompany } from "./features/company/RequireCompany";
import { ProgramDetailPage } from "./features/programs/ProgramDetailPage";
import { ProgramListPage } from "./features/programs/ProgramListPage";
import { RecommendPage } from "./features/recommend/RecommendPage";
import { Layout } from "./shared/components/Layout";

// 지원사업 목록·상세는 공개 공고라 로그인·기업정보 없이 볼 수 있다. 기업정보 화면은 로그인이 필요하다.
// AI 검색·맞춤 추천은 로그인하면 들어갈 수 있지만, 기업정보 등록 전에는 화면 안에서 입력을 안내하고 기능을 잠근다
// (AI 검색은 입력·버튼 비활성, 맞춤 추천은 안내 화면). Spring도 같은 규칙으로 막는다.
const RECOMMEND_NOTICE = {
  title: "내 기업 맞춤 지원사업 추천",
  description: "맞춤 추천은 등록한 기업정보(기업 규모·영업 상태 등)로 공고를 고르고 지원 자격을 확인합니다. 회사명만 넣어도 시작할 수 있고, 모르는 항목은 비워 두세요.",
};

export function App() {
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route element={<Layout />}>
        <Route path="/" element={<Navigate to="/ai" replace />} />
        <Route path="/ai" element={<RequireAuth><AiSearchPage /></RequireAuth>} />
        {/* 주소의 workflowId로 새로고침해도 진행 상태를 복원한다(같은 화면이 유지되도록 선택 경로 하나로 둔다). */}
        <Route path="/recommend/:workflowId?" element={<RequireAuth><RequireCompany notice={RECOMMEND_NOTICE}><RecommendPage /></RequireCompany></RequireAuth>} />
        <Route path="/programs" element={<ProgramListPage />} />
        <Route path="/programs/:pblancId" element={<ProgramDetailPage />} />
        <Route path="/company" element={<RequireAuth><CompanyPage /></RequireAuth>} />
        <Route path="/account" element={<RequireAuth><AccountPage /></RequireAuth>} />
        <Route path="*" element={<Navigate to="/ai" replace />} />
      </Route>
    </Routes>
  );
}
