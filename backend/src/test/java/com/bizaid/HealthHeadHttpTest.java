package com.bizaid;

import static org.assertj.core.api.Assertions.assertThat;

import java.io.ByteArrayOutputStream;
import java.io.InputStream;
import java.io.OutputStream;
import java.net.Socket;
import java.nio.charset.StandardCharsets;
import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.server.LocalServerPort;

/**
 * 실제 내장 Tomcat에 HEAD /api/health를 보내 운영 profile에서 로그인 없이 200이고 본문이 없는지 확인한다.
 * WHY: MockMvc는 HEAD 응답 본문을 지우지 않으므로 본문 없음은 실제 서버로만 확인할 수 있다. 감시 도구는 HEAD만 보낸다.
 */
@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT, properties = {"spring.profiles.active=prod",
        "spring.datasource.url=jdbc:h2:mem:healthhead;MODE=MySQL;DATABASE_TO_LOWER=TRUE;DB_CLOSE_DELAY=-1",
        "spring.flyway.locations=filesystem:../migrations", "bizaid.ai.base-url=http://127.0.0.1:9"})
class HealthHeadHttpTest {

    @LocalServerPort
    int port;

    @Test
    void headHealthReturns200WithoutBodyAndGetKeepsJson() throws Exception {
        String head = exchange("HEAD");
        assertThat(head).startsWith("HTTP/1.1 200");
        // 헤더 끝(빈 줄) 뒤에 아무 byte도 없어야 한다.
        assertThat(head.substring(head.indexOf("\r\n\r\n") + 4)).isEmpty();
        String get = exchange("GET");
        assertThat(get).startsWith("HTTP/1.1 200");
        // GET 본문은 chunked 전송이라 길이 줄 사이에 JSON이 온다.
        assertThat(get).contains("\r\n\r\n").contains("{\"status\":\"ok\"}");
    }

    private String exchange(String method) throws Exception {
        try (Socket socket = new Socket("127.0.0.1", port)) {
            socket.setSoTimeout(5000);
            OutputStream out = socket.getOutputStream();
            out.write((method + " /api/health HTTP/1.1\r\nHost: localhost\r\nConnection: close\r\n\r\n").getBytes(StandardCharsets.US_ASCII));
            out.flush();
            InputStream in = socket.getInputStream();
            ByteArrayOutputStream buffer = new ByteArrayOutputStream();
            in.transferTo(buffer);
            return buffer.toString(StandardCharsets.UTF_8);
        }
    }
}
