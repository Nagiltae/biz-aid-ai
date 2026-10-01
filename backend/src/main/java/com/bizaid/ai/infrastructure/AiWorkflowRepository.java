package com.bizaid.ai.infrastructure;

import com.bizaid.ai.domain.AiWorkflow;
import org.springframework.data.jpa.repository.JpaRepository;

public interface AiWorkflowRepository extends JpaRepository<AiWorkflow, Long> {
}
