import { useQuery } from "@tanstack/react-query";
import { useAuth } from "../auth/AuthContext";
import { companyApi } from "./companyApi";

// 기업정보 등록 여부는 메뉴·보호 routing·기업정보 화면이 함께 쓴다. 같은 query key 하나로 공유하고,
// 등록·수정하면 이 값을 바로 바꿔 모든 화면이 함께 갱신된다. 로그아웃하면 AuthContext가 cache를 비운다.
export const MY_COMPANY_KEY = ["company"] as const;

export function useMyCompany() {
  const { user } = useAuth();
  return useQuery({ queryKey: MY_COMPANY_KEY, queryFn: companyApi.find, enabled: user !== null, retry: false });
}
