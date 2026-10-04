import { useMutation, useQuery } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";
import { authApi } from "./authApi";
import { useAuth } from "./AuthContext";

/** 체험하기: 설정으로 켜져 있을 때만 버튼을 보이고, 누르면 새 체험 계정으로 로그인해 AI 검색으로 보낸다. */
export function useTrial() {
  const { accept } = useAuth();
  const navigate = useNavigate();
  const status = useQuery({ queryKey: ["trial-status"], queryFn: authApi.trialStatus, staleTime: 60_000 });
  const start = useMutation({
    mutationFn: authApi.startTrial,
    onSuccess: (response) => {
      accept(response);
      navigate("/ai", { replace: true });
    },
  });
  return { enabled: status.data?.enabled === true, start };
}
