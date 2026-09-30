import { NavLink, Outlet, useNavigate } from "react-router-dom";
import { useAuth } from "../../features/auth/AuthContext";

export function Layout() {
  const { user, logout } = useAuth();
  const navigate = useNavigate();
  const link = ({ isActive }: { isActive: boolean }) => (isActive ? "nav-link active" : "nav-link");

  return (
    <div className="app">
      <header className="header">
        <div className="header-inner">
          <NavLink to="/ai" className="brand">
            BizAid <span className="brand-sub">지원사업 찾기</span>
          </NavLink>
          <nav className="nav" aria-label="주요 메뉴">
            <NavLink to="/ai" className={link}>AI 검색</NavLink>
            <NavLink to="/programs" className={link}>지원사업</NavLink>
            <NavLink to="/company" className={link}>내 기업정보</NavLink>
          </nav>
          <div className="account">
            {user ? (
              <>
                <span className="muted account-name">{user.displayName}님</span>
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
