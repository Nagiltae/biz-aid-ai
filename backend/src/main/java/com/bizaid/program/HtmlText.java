package com.bizaid.program;

import java.util.Set;
import org.jsoup.Jsoup;
import org.jsoup.nodes.Element;
import org.jsoup.nodes.Node;
import org.jsoup.nodes.TextNode;
import org.jsoup.select.NodeTraversor;
import org.jsoup.select.NodeVisitor;

/**
 * 기업마당 요약(summary_html)을 화면용 일반 텍스트로 바꾼다.
 * WHY: 원문 HTML을 React에서 그대로 렌더링하면 외부 데이터의 script·이벤트 속성이 실행될 수 있다(XSS).
 * 서버에서 글자(TextNode)만 꺼내고 문단·줄바꿈만 개행으로 남겨 React는 텍스트로만 표시한다. DB 원문은 바꾸지 않는다.
 */
final class HtmlText {

    private static final Set<String> BLOCKS = Set.of("p", "div", "li", "tr", "h1", "h2", "h3", "h4", "h5", "h6");

    private HtmlText() {
    }

    static String toPlainText(String html) {
        if (html == null || html.isBlank()) {
            return null;
        }
        StringBuilder out = new StringBuilder();
        // script·style 내용은 TextNode가 아니라서 자연히 제외된다.
        NodeTraversor.traverse(new NodeVisitor() {
            @Override
            public void head(Node node, int depth) {
                if (node instanceof TextNode text) {
                    out.append(text.getWholeText());
                } else if (node instanceof Element element && element.nameIs("br")) {
                    out.append('\n');
                }
            }

            @Override
            public void tail(Node node, int depth) {
                if (node instanceof Element element && BLOCKS.contains(element.normalName())) {
                    out.append('\n');
                }
            }
        }, Jsoup.parse(html).body());
        // 빈 문단이 여러 개 이어진 원문을 읽기 좋게 최대 한 줄 공백으로 줄인다.
        return out.toString().replace(' ', ' ').lines().map(String::strip)
                .reduce((left, right) -> left + "\n" + right).orElse("").replaceAll("\n{3,}", "\n\n").strip();
    }
}
