package com.bizaid.company.infrastructure;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.List;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;

/**
 * 기업 지역(광역 지자체) 표준명 목록. 값은 코드에 적지 않고 공통 계약(contracts/schemas/company-region.contract.json)에서 읽는다.
 * FastAPI 후보 필터·React 선택지와 같은 목록을 쓰기 위해서다(2026-10-03 사용자 결정, IMP-019).
 * 계약 파일을 읽지 못하면 시작하지 않는다(잘못된 목록으로 저장을 받지 않게).
 */
@Component
public class RegionCatalog {

    private final List<String> regions;

    public RegionCatalog(@Value("${bizaid.contracts-path}") String contractsPath, ObjectMapper objectMapper) throws IOException {
        Path file = Path.of(contractsPath, "schemas", "company-region.contract.json");
        JsonNode root = objectMapper.readTree(Files.readString(file));
        List<String> values = new ArrayList<>();
        root.path("regions").forEach(node -> values.add(node.asText()));
        if (values.isEmpty()) {
            throw new IllegalStateException("company region contract has no regions");
        }
        this.regions = List.copyOf(values);
    }

    public List<String> regions() {
        return regions;
    }

    public boolean contains(String region) {
        return regions.contains(region);
    }
}
