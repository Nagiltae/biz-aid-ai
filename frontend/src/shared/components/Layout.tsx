import { NavLink, Outlet, useNavigate } from "react-router-dom";
import { useAuth } from "../../features/auth/AuthContext";
import { useMyCompany } from "../../features/company/useMyCompany";

export function Layout() {
  const { user, logout } = useAuth();
  const company = useMyCompany();
  const navigate = useNavigate();
  const link = ({ isActive }: { isActive: boolean }) => (isActive ? "nav-link active" : "nav-link");
  // 로그인했지만 기업정보가 없으면 AI 기능 메뉴를 잠근다(누르면 어차피 등록 화면으로 간다). 지원사업은 공개라 그대로 둔다.
  const locked = user !== null && company.data === null;
  const aiLink = (to: string, label: string) =>
    locked ? (
      <span className="nav-link disabled" aria-disabled="true" title="기업정보를 먼저 등록해 주세요">{label}</span>
    ) : (
      <NavLink to={to} className={link}>{label}</NavLink>
    );

  return (
    <div className="app">
      <header className="header">
        <div className="header-inner">
          <NavLink to="/ai" className="brand">
            BizAid <span className="brand-sub">지원사업 찾기</span>
          </NavLink>
          <nav className="nav" aria-label="주요 메뉴">
            {aiLink("/ai", "AI 검색")}
            {aiLink("/recommend", "맞춤 추천")}
            <NavLink to="/programs" className={link}>지원사업</NavLink>
          </nav>
          <div className="account">
            {user ? (
              <>
                <span className="muted account-name">{user.displayName}님</span>
                {/* 계정 영역에 두어 "내 정보 관리"로 보이게 한다. */}
                <NavLink to="/company" className={({ isActive }) => (isActive ? "button small active" : "button small")}>
                  내 기업정보
                </NavLink>
                <button type="button" className="button small" onClick={() => logout().then(() => navigate("/login"))}>
                  로그아웃
                </button>
              </>
            ) : (
              <NavLink to="/login" className="button small primary">로그인</NavLink>
            )}
          </div>
        </div>
      </header>
      <main className="main">
        <Outlet />
      </main>
    </div>
  );
}
