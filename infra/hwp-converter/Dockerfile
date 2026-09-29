# HWP → PDF 전용 변환 이미지. host에 LibreOffice를 설치하지 않고 이 이미지로만 변환한다.
# 기반 이미지는 digest, H2Orestart는 release SHA-256으로 고정한다. LibreOffice 실제 버전은 빌드 때 기록해 parse_key에 넣는다.
FROM debian:trixie-slim@sha256:a99cfc517144bc59b1978475ec53b46ecabec7e43635402ee5b77cc54cd1b20a

ARG H2ORESTART_VERSION=v0.7.14
ARG H2ORESTART_SHA256=cbea23bc37861361bbc534bc0675e5bc67b36f712072490f82a9bf410d7c04d8

# H2Orestart는 Java 확장이므로 JRE와 LibreOffice Java 연동이 필요하다. 한글 본문 렌더링에 한글 글꼴을 넣는다.
RUN apt-get update \
    && apt-get install -y --no-install-recommends libreoffice-writer-nogui libreoffice-java-common \
       default-jre-headless fonts-nanum fonts-noto-cjk ca-certificates curl \
    && rm -rf /var/lib/apt/lists/*

RUN curl -fsSL -o /tmp/H2Orestart.oxt \
       "https://github.com/ebandal/H2Orestart/releases/download/${H2ORESTART_VERSION}/H2Orestart.oxt" \
    && echo "${H2ORESTART_SHA256}  /tmp/H2Orestart.oxt" | sha256sum -c - \
    && unopkg add --shared /tmp/H2Orestart.oxt \
    && rm /tmp/H2Orestart.oxt \
    && mkdir -p /opt/bizaid \
    && soffice --version | head -1 > /opt/bizaid/libreoffice-version \
    && echo "${H2ORESTART_VERSION} ${H2ORESTART_SHA256}" > /opt/bizaid/h2orestart-version

# 변환은 네트워크 없이 호출자 uid로 실행하며 LibreOffice profile은 매 실행의 /tmp에만 둔다.
ENV HOME=/tmp
WORKDIR /work
ENTRYPOINT ["soffice", "--headless", "--norestore", "--nologo", "-env:UserInstallation=file:///tmp/lo-profile", \
            "--convert-to", "pdf", "--outdir", "/work/out"]
