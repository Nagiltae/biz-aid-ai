package com.bizaid.conversation;

import java.util.List;
import org.springframework.data.jpa.repository.JpaRepository;

public interface ConversationRepository extends JpaRepository<Conversation, Long> {

    List<Conversation> findTop50ByUserIdOrderByUpdatedAtDescIdDesc(Long userId);
}
