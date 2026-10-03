package com.bizaid.conversation.infrastructure;

import org.springframework.data.repository.query.Param;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.jpa.repository.Modifying;
import com.bizaid.conversation.domain.Message;
import java.util.List;
import org.springframework.data.jpa.repository.JpaRepository;

public interface MessageRepository extends JpaRepository<Message, Long> {

    List<Message> findByConversationIdOrderByIdAsc(Long conversationId);

    @Modifying
    @Query("delete from Message m where m.conversation.id = :conversationId")
    int deleteAllByConversation(@Param("conversationId") Long conversationId);

    // BOUNDARY: 회원 탈퇴는 그 사용자의 대화에 속한 메시지만 지운다(대화 소유자 기준 subquery).
    @Modifying
    @Query("delete from Message m where m.conversation.id in (select c.id from Conversation c where c.userId = :userId)")
    int deleteAllByUser(@Param("userId") Long userId);
}
