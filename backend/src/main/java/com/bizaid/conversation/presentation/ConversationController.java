package com.bizaid.conversation.presentation;

import com.bizaid.auth.domain.AuthUser;
import com.bizaid.conversation.application.ConversationDtos;
import com.bizaid.conversation.application.ConversationService;
import jakarta.validation.Valid;
import java.util.List;
import org.springframework.http.HttpStatus;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.web.bind.annotation.DeleteMapping;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.ResponseStatus;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/conversations")
public class ConversationController {

    private final ConversationService conversationService;

    public ConversationController(ConversationService conversationService) {
        this.conversationService = conversationService;
    }

    @PostMapping
    @ResponseStatus(HttpStatus.CREATED)
    public ConversationDtos.ConversationResponse create(@AuthenticationPrincipal AuthUser user,
                                                        @Valid @RequestBody ConversationRequests.CreateConversationRequest request) {
        return conversationService.create(user.id(), request.title());
    }

    @GetMapping
    public List<ConversationDtos.ConversationResponse> list(@AuthenticationPrincipal AuthUser user) {
        return conversationService.list(user.id());
    }

    @DeleteMapping("/{conversationId}")
    @ResponseStatus(HttpStatus.NO_CONTENT)
    public void delete(@AuthenticationPrincipal AuthUser user, @PathVariable Long conversationId) {
        conversationService.delete(user.id(), conversationId);
    }

    @GetMapping("/{conversationId}/messages")
    public List<ConversationDtos.MessageResponse> messages(@AuthenticationPrincipal AuthUser user,
                                                           @PathVariable Long conversationId) {
        return conversationService.messages(user.id(), conversationId);
    }

    @PostMapping("/{conversationId}/messages")
    @ResponseStatus(HttpStatus.CREATED)
    public ConversationDtos.MessageResponse addMessage(@AuthenticationPrincipal AuthUser user, @PathVariable Long conversationId,
                                                       @Valid @RequestBody ConversationRequests.CreateMessageRequest request) {
        return conversationService.addUserMessage(user.id(), conversationId, request.content());
    }
}
