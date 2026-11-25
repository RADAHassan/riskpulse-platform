# ---------- Étape 1 : construire le jar ----------
FROM maven:3.9-eclipse-temurin-17 AS build
WORKDIR /build

# Le POM parent + le module (le module a besoin du parent)
COPY pom.xml .
COPY customer-service/pom.xml customer-service/pom.xml
COPY customer-service/src customer-service/src

# -pl : construire seulement ce module ; -am : avec le parent dont il dépend
# Le cache Maven est gardé entre les builds (BuildKit)
RUN --mount=type=cache,target=/root/.m2 \
    mvn -B -pl customer-service -am clean package -DskipTests

# ---------- Étape 2 : exécuter ----------
FROM eclipse-temurin:17-jre
WORKDIR /app

RUN apt-get update \
 && apt-get install -y --no-install-recommends curl \
 && rm -rf /var/lib/apt/lists/* \
 && useradd --system --no-create-home appuser

# Ne pas lancer l'application en root
USER appuser

COPY --from=build /build/customer-service/target/customer-service-0.1.0-SNAPSHOT.jar app.jar

EXPOSE 8082
ENTRYPOINT ["java", "-XX:MaxRAMPercentage=75", "-jar", "app.jar"]