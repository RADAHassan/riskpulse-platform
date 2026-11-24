# syntax=docker/dockerfile:1.7
# Shared, layered, non-root image for every Spring Boot service.
#   docker build -f backend/Dockerfile --build-arg MODULE=risk-service --build-arg PORT=8084 -t riskpulse-risk-service .
# Build context: repository root (transaction-service bundles ml/artifacts/demo_transactions.csv).

FROM maven:3.9-eclipse-temurin-21@sha256:99e61abcff91a9b1333463bd8451fb18495d6eba9250ac66a338b518f8278320 AS build
ARG MODULE
WORKDIR /build
COPY backend backend
COPY ml/artifacts/demo_transactions.csv ml/artifacts/demo_transactions.csv
RUN --mount=type=cache,target=/root/.m2 \
    mvn -B -ntp -f backend/pom.xml -pl ${MODULE} -am -DskipTests -Djacoco.skip=true package \
    && mkdir -p /extracted \
    && java -Djarmode=tools -jar backend/${MODULE}/target/${MODULE}-*-SNAPSHOT.jar extract --layers --launcher --destination /extracted

FROM eclipse-temurin:21-jre-alpine@sha256:5d7689f47d670aca766b9503a70bccc2d73b4eb9221ae8f714ae958313c4ce70
ARG MODULE
ARG PORT=8080
LABEL org.opencontainers.image.source="https://github.com/RADAHassan/riskpulse-platform" \
      org.opencontainers.image.title="riskpulse-${MODULE}"
RUN addgroup -g 10001 -S app && adduser -u 10001 -S -G app -H -s /sbin/nologin app
WORKDIR /app
# Layers ordered from the least to the most frequently changing -> small, cache-friendly image updates
COPY --from=build /extracted/dependencies/ ./
COPY --from=build /extracted/spring-boot-loader/ ./
COPY --from=build /extracted/snapshot-dependencies/ ./
COPY --from=build /extracted/application/ ./
USER 10001:10001
ENV JAVA_TOOL_OPTIONS="-XX:MaxRAMPercentage=75 -XX:+ExitOnOutOfMemoryError -Djava.security.egd=file:/dev/./urandom" \
    SERVER_PORT=${PORT}
EXPOSE ${PORT}
HEALTHCHECK --interval=15s --timeout=3s --start-period=60s --retries=5 \
  CMD wget -q -O /dev/null "http://127.0.0.1:${SERVER_PORT}/actuator/health/liveness" || exit 1
ENTRYPOINT ["java", "org.springframework.boot.loader.launch.JarLauncher"]
