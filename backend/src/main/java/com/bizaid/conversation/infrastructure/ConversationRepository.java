package com.bizaid.conversation.infrastructure;

import org.springframework.data.repository.query.Param;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.jpa.repository.Modifying;
import com.bizaid.conversation.domain.Conversation;
import java.util.List;
import org.springframework.data.jpa.repository.JpaRepository;

public interface ConversationRepository extends JpaRepository<Conversation, Long> {

    List<Conversation> findTop50ByUserIdOrderByUpdatedAtDescIdDesc(Long userId);

    @Modifying
    @Query("delete from Conversation c where c.userId = :userId")
    int deleteAllByUser(@Param("userId") Long userId);
}
