# 1단계: Gradle로 실행 jar를 만든다(테스트는 개발 단계에서 따로 실행한다).
FROM gradle:8.14-jdk21 AS build
WORKDIR /app
COPY settings.gradle build.gradle ./
COPY src ./src
RUN gradle bootJar --no-daemon -q

# 2단계: JRE만 있는 작은 이미지에서 실행한다. DB 접속정보·JWT secret은 실행 시 환경변수로 받는다.
FROM eclipse-temurin:21-jre
WORKDIR /app
RUN useradd --system --uid 10001 bizaid
COPY --from=build /app/build/libs/*.jar app.jar
USER bizaid
EXPOSE 8080
ENTRYPOINT ["java", "-jar", "/app/app.jar"]
