package com.bizaid.company.presentation;

import com.bizaid.auth.domain.AuthUser;
import com.bizaid.company.application.CompanyResponse;
import com.bizaid.company.application.CompanyService;
import jakarta.validation.Valid;
import org.springframework.http.HttpStatus;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.PutMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.ResponseStatus;
import org.springframework.web.bind.annotation.RestController;

/** 내 기업정보 API. 경로에 기업 id를 받지 않고 로그인 사용자로만 대상을 정해 타인 정보 접근을 원천적으로 막는다. */
@RestController
@RequestMapping("/api/company")
public class CompanyController {

    private final CompanyService companyService;

    public CompanyController(CompanyService companyService) {
        this.companyService = companyService;
    }

    @GetMapping
    public CompanyResponse get(@AuthenticationPrincipal AuthUser user) {
        return companyService.get(user.id());
    }

    @PostMapping
    @ResponseStatus(HttpStatus.CREATED)
    public CompanyResponse create(@AuthenticationPrincipal AuthUser user, @Valid @RequestBody CompanyRequest request) {
        return companyService.create(user.id(), request.toDetails());
    }

    @PutMapping
    public CompanyResponse update(@AuthenticationPrincipal AuthUser user, @Valid @RequestBody CompanyRequest request) {
        return companyService.update(user.id(), request.toDetails());
    }
}
