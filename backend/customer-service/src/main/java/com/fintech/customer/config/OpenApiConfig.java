package com.fintech.customer.config;

import io.swagger.v3.oas.models.Components;
import io.swagger.v3.oas.models.OpenAPI;
import io.swagger.v3.oas.models.info.Info;
import io.swagger.v3.oas.models.security.SecurityScheme;
import org.springdoc.core.models.GroupedOpenApi;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import io.swagger.v3.oas.models.security.SecurityRequirement;
@Configuration
public class OpenApiConfig {

    @Bean
    public OpenAPI customerOpenApi() {
        return new OpenAPI()
                .info(new Info()
                        .title("customer-service")
                        .version("1.0")
                        .description("""
                                Profils clients et comptes (contrat C-01 a C-10).
                                En production, l'identite est transmise par le Gateway dans les en-tetes
                                X-User-Id, X-User-Role (CLIENT, ANALYST, ADMIN) et X-User-Email.
                                Dans Swagger, renseigne-les via le bouton Authorize.
                                Toutes les erreurs suivent le format unique : timestamp, status, error,
                                code, message, path, correlationId, details."""))
                .components(new Components()
                        .addSecuritySchemes("userId", header("X-User-Id"))
                        .addSecuritySchemes("userRole", header("X-User-Role"))
                        .addSecuritySchemes("userEmail", header("X-User-Email"))
                        .addSecuritySchemes("serviceToken", header("X-Service-Token")))
                .addSecurityItem(new SecurityRequirement()
                        .addList("userId")
                        .addList("userRole")
                        .addList("userEmail"));
    }

    private SecurityScheme header(String name) {
        return new SecurityScheme().type(SecurityScheme.Type.APIKEY)
                .in(SecurityScheme.In.HEADER).name(name);
    }

    /** Documentation destinee a C : endpoints publics uniquement. */
    @Bean
    public GroupedOpenApi publicApi() {
        return GroupedOpenApi.builder().group("public").pathsToMatch("/api/v1/**").build();
    }

    /** Endpoints internes : jamais routes par le Gateway. */
    @Bean
    public GroupedOpenApi internalApi() {
        return GroupedOpenApi.builder().group("internal").pathsToMatch("/internal/**").build();
    }
}