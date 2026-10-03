-- 기업 지역을 광역 지자체 표준명(contracts/schemas/company-region.contract.json regions)으로 바꾼다(2026-10-03 사용자 결정, IMP-019).
-- RISK: 2026-10-03 사용자가 TAB/개행 미제거 → NULL, 광주시 prefix 오분류 경계를 수용하고 적용 승인했다. 현재 해당 값은 없으며 운영 기업 데이터 없음·Spring 표준명 입력 검증을 전제로 한다.
-- 공백을 뺀 값이 계약 별칭으로 시작하면 그 표준명, 어떤 별칭에도 맞지 않으면 NULL이다. 긴 별칭을 먼저 본다.
UPDATE companies
SET region = CASE
        WHEN REPLACE(region, ' ', '') LIKE '전남광주통합특별시%' THEN '전남광주통합특별시'
        WHEN REPLACE(region, ' ', '') LIKE '강원특별자치도%' THEN '강원특별자치도'
        WHEN REPLACE(region, ' ', '') LIKE '세종특별자치시%' THEN '세종특별자치시'
        WHEN REPLACE(region, ' ', '') LIKE '전북특별자치도%' THEN '전북특별자치도'
        WHEN REPLACE(region, ' ', '') LIKE '제주특별자치도%' THEN '제주특별자치도'
        WHEN REPLACE(region, ' ', '') LIKE '광주광역시%' THEN '전남광주통합특별시'
        WHEN REPLACE(region, ' ', '') LIKE '대구광역시%' THEN '대구광역시'
        WHEN REPLACE(region, ' ', '') LIKE '대전광역시%' THEN '대전광역시'
        WHEN REPLACE(region, ' ', '') LIKE '부산광역시%' THEN '부산광역시'
        WHEN REPLACE(region, ' ', '') LIKE '서울특별시%' THEN '서울특별시'
        WHEN REPLACE(region, ' ', '') LIKE '울산광역시%' THEN '울산광역시'
        WHEN REPLACE(region, ' ', '') LIKE '인천광역시%' THEN '인천광역시'
        WHEN REPLACE(region, ' ', '') LIKE '경상남도%' THEN '경상남도'
        WHEN REPLACE(region, ' ', '') LIKE '경상북도%' THEN '경상북도'
        WHEN REPLACE(region, ' ', '') LIKE '전라남도%' THEN '전남광주통합특별시'
        WHEN REPLACE(region, ' ', '') LIKE '전라북도%' THEN '전북특별자치도'
        WHEN REPLACE(region, ' ', '') LIKE '충청남도%' THEN '충청남도'
        WHEN REPLACE(region, ' ', '') LIKE '충청북도%' THEN '충청북도'
        WHEN REPLACE(region, ' ', '') LIKE '강원도%' THEN '강원특별자치도'
        WHEN REPLACE(region, ' ', '') LIKE '경기도%' THEN '경기도'
        WHEN REPLACE(region, ' ', '') LIKE '대구시%' THEN '대구광역시'
        WHEN REPLACE(region, ' ', '') LIKE '대전시%' THEN '대전광역시'
        WHEN REPLACE(region, ' ', '') LIKE '부산시%' THEN '부산광역시'
        WHEN REPLACE(region, ' ', '') LIKE '서울시%' THEN '서울특별시'
        WHEN REPLACE(region, ' ', '') LIKE '세종시%' THEN '세종특별자치시'
        WHEN REPLACE(region, ' ', '') LIKE '울산시%' THEN '울산광역시'
        WHEN REPLACE(region, ' ', '') LIKE '인천시%' THEN '인천광역시'
        WHEN REPLACE(region, ' ', '') LIKE '제주도%' THEN '제주특별자치도'
        WHEN REPLACE(region, ' ', '') LIKE '강원%' THEN '강원특별자치도'
        WHEN REPLACE(region, ' ', '') LIKE '경기%' THEN '경기도'
        WHEN REPLACE(region, ' ', '') LIKE '경남%' THEN '경상남도'
        WHEN REPLACE(region, ' ', '') LIKE '경북%' THEN '경상북도'
        WHEN REPLACE(region, ' ', '') LIKE '광주%' THEN '전남광주통합특별시'
        WHEN REPLACE(region, ' ', '') LIKE '대구%' THEN '대구광역시'
        WHEN REPLACE(region, ' ', '') LIKE '대전%' THEN '대전광역시'
        WHEN REPLACE(region, ' ', '') LIKE '부산%' THEN '부산광역시'
        WHEN REPLACE(region, ' ', '') LIKE '서울%' THEN '서울특별시'
        WHEN REPLACE(region, ' ', '') LIKE '세종%' THEN '세종특별자치시'
        WHEN REPLACE(region, ' ', '') LIKE '울산%' THEN '울산광역시'
        WHEN REPLACE(region, ' ', '') LIKE '인천%' THEN '인천광역시'
        WHEN REPLACE(region, ' ', '') LIKE '전남%' THEN '전남광주통합특별시'
        WHEN REPLACE(region, ' ', '') LIKE '전북%' THEN '전북특별자치도'
        WHEN REPLACE(region, ' ', '') LIKE '제주%' THEN '제주특별자치도'
        WHEN REPLACE(region, ' ', '') LIKE '충남%' THEN '충청남도'
        WHEN REPLACE(region, ' ', '') LIKE '충북%' THEN '충청북도'
        ELSE NULL
    END
WHERE region IS NOT NULL;

ALTER TABLE companies
    MODIFY COLUMN region VARCHAR(100) NULL
        COMMENT '사업장 소재 광역 지자체 표준명(company-region 계약의 16개 중 하나). 맞춤 추천에서 다른 광역 지자체 소관 공고를 후보에서 뺄 때 쓴다.';
