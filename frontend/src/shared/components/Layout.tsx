import { NavLink, Outlet, useNavigate } from "react-router-dom";
import { useAuth } from "../../features/auth/AuthContext";

export function Layout() {
  const { user, logout } = useAuth();
  const navigate = useNavigate();
  const link = ({ isActive }: { isActive: boolean }) => (isActive ? "nav-link active" : "nav-link");
  // 기업정보가 없어도 메뉴는 잠그지 않는다. AI 검색·맞춤 추천은 화면 안에서 기업정보 입력을 안내한다.

  return (
    <div className="app">
      <header className="header">
        <div className="header-inner">
          <NavLink to="/ai" className="brand">
            BizAid <span className="brand-sub">지원사업 찾기</span>
          </NavLink>
          <nav className="nav" aria-label="주요 메뉴">
            <NavLink to="/ai" className={link}>AI 검색</NavLink>
            <NavLink to="/recommend" className={link}>맞춤 추천</NavLink>
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
