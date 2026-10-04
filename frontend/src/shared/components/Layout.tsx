import { Link, NavLink, Outlet, useNavigate } from "react-router-dom";
import { useAuth } from "../../features/auth/AuthContext";
import { DATA_SOURCE } from "../../features/legal/legalVersions";

export function Layout() {
  const { user, logout } = useAuth();
  const navigate = useNavigate();
  const link = ({ isActive }: { isActive: boolean }) => (isActive ? "nav-link active" : "nav-link");
  // 기업정보가 없어도 메뉴는 잠그지 않는다. AI 검색·맞춤 추천은 화면 안에서 기업정보 입력을 안내한다.

  return (
    <div className="app">
      <header className="header">
        <div className="header-inner">
          <NavLink to="/" className="brand">
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
                {user.trial && <span className="badge trial-badge">체험 중</span>}
                {/* 계정 영역에 두어 "내 정보 관리"로 보이게 한다. */}
                <NavLink to="/company" className={({ isActive }) => (isActive ? "button small active" : "button small")}>
                  내 기업정보
                </NavLink>
                <NavLink to="/account" className={({ isActive }) => (isActive ? "button small active" : "button small")}>
                  계정
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
      {user?.trial && (
        <div className="trial-banner" role="status" aria-label="체험 중 안내">
          <span>
            <strong>체험 중</strong>입니다. 예시 회사 정보(경기도·소상공인)로 이용하며, 24시간 뒤 대화와 기록이 모두 지워집니다.
          </span>
          {/* 가입 탭을 연다. 가입을 마치면 그때 체험 세션을 끝낸다(LoginPage). */}
          <button type="button" className="button small primary" onClick={() => navigate("/login", { state: { mode: "signup" } })}>
            회원가입
          </button>
        </div>
      )}
      <main className="main">
        <Outlet />
      </main>
      <footer className="footer">
        <div className="footer-inner">
          <p>
            공고 정보: <a href={DATA_SOURCE.url} target="_blank" rel="noopener noreferrer">{DATA_SOURCE.name}</a> 공공데이터 활용.
            각 공고의 원문은 공고 상세의 "공고 원문 보기"에서 확인하세요.
          </p>
          <p>AI 판정은 참고용입니다. 최종 자격은 공고문과 주관기관에 확인하세요.</p>
          <p className="footer-links">
            <Link to="/terms">이용약관</Link>
            <Link to="/privacy">개인정보처리방침</Link>
          </p>
        </div>
      </footer>
    </div>
  );
}
