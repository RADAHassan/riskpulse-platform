package com.riskpulse.gateway;

import java.util.Arrays;
import java.util.List;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.http.HttpStatus;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.oauth2.jwt.JwtValidators;
import org.springframework.security.oauth2.jwt.NimbusReactiveJwtDecoder;
import org.springframework.security.oauth2.jwt.ReactiveJwtDecoder;
import org.springframework.security.oauth2.server.resource.authentication.JwtAuthenticationConverter;
import org.springframework.security.oauth2.server.resource.authentication.ReactiveJwtAuthenticationConverterAdapter;
import org.springframework.security.web.server.SecurityWebFilterChain;
import org.springframework.security.web.server.header.ReferrerPolicyServerHttpHeadersWriter;
import org.springframework.web.cors.CorsConfiguration;
import org.springframework.web.cors.reactive.CorsWebFilter;
import org.springframework.web.cors.reactive.UrlBasedCorsConfigurationSource;

/**
 * Edge security: JWT (RS256, JWKS from auth-service) is validated here AND again by every service.
 * Coarse role gates live here; fine-grained ownership checks (BOLA) live in the services.
 */
@Configuration
@EnableWebFluxSecurity
public class GatewaySecurityConfig {

    @Bean
    SecurityWebFilterChain springSecurityFilterChain(ServerHttpSecurity http, ReactiveJwtDecoder decoder) {
        JwtAuthenticationConverter converter = new JwtAuthenticationConverter();
        converter.setJwtGrantedAuthoritiesConverter(jwt -> {
            List<String> roles = jwt.getClaimAsStringList("roles");
            return roles == null ? List.of() : roles.stream()
                    .map(r -> (org.springframework.security.core.GrantedAuthority) new SimpleGrantedAuthority("ROLE_" + r))
                    .toList();
        });

        return http
                .csrf(ServerHttpSecurity.CsrfSpec::disable)
                .httpBasic(ServerHttpSecurity.HttpBasicSpec::disable)
                .formLogin(ServerHttpSecurity.FormLoginSpec::disable)
                .logout(ServerHttpSecurity.LogoutSpec::disable)
                .cors(ServerHttpSecurity.CorsSpec::disable)
                .headers(h -> h
                        .contentSecurityPolicy(c -> c.policyDirectives("default-src 'none'; frame-ancestors 'none'"))
                        .frameOptions(f -> f.mode(org.springframework.security.web.server.header.XFrameOptionsServerHttpHeadersWriter.Mode.DENY))
                        .hsts(s -> s.includeSubdomains(true).maxAge(java.time.Duration.ofDays(365)))
                        .referrerPolicy(r -> r.policy(ReferrerPolicyServerHttpHeadersWriter.ReferrerPolicy.NO_REFERRER)))
                .authorizeExchange(a -> a
                        .pathMatchers(HttpMethod.OPTIONS, "/**").permitAll()
                        .pathMatchers("/actuator/health/**", "/actuator/prometheus", "/openapi.yaml").permitAll()
                        .pathMatchers(HttpMethod.POST, "/api/auth/login", "/api/auth/refresh", "/api/auth/logout").permitAll()
                        .pathMatchers("/api/auth/users").hasRole("ADMIN")
                        .pathMatchers("/api/transactions/simulate").hasRole("ADMIN")
                        .pathMatchers("/api/audit/**", "/api/reviews/**", "/api/risk/stats", "/api/ml/**")
                        .hasAnyRole("ADMIN", "ANALYST")
                        .pathMatchers("/api/**").authenticated()
                        .anyExchange().denyAll())
                .oauth2ResourceServer(o -> o
                        .jwt(j -> j.jwtDecoder(decoder).jwtAuthenticationConverter(new ReactiveJwtAuthenticationConverterAdapter(converter)))
                        .authenticationEntryPoint((ex, e) -> Problems.write(ex.getResponse(), HttpStatus.UNAUTHORIZED,
                                "Authentication required"))
                        .accessDeniedHandler((ex, e) -> Problems.write(ex.getResponse(), HttpStatus.FORBIDDEN, "Access denied")))
                .exceptionHandling(e -> e
                        .authenticationEntryPoint((ex, ae) -> Problems.write(ex.getResponse(), HttpStatus.UNAUTHORIZED,
                                "Authentication required"))
                        .accessDeniedHandler((ex, ade) -> Problems.write(ex.getResponse(), HttpStatus.FORBIDDEN, "Access denied")))
                .build();
    }

    @Bean
    ReactiveJwtDecoder jwtDecoder(@Value("${riskpulse.security.jwks-uri}") String jwksUri,
                                  @Value("${riskpulse.security.issuer}") String issuer) {
        NimbusReactiveJwtDecoder decoder = NimbusReactiveJwtDecoder.withJwkSetUri(jwksUri).build();
        decoder.setJwtValidator(JwtValidators.createDefaultWithIssuer(issuer));
        return decoder;
    }

    /** CORS is answered before authentication (preflight carries no token) with an explicit origin allow-list. */
    @Bean
    @org.springframework.core.annotation.Order(org.springframework.core.Ordered.HIGHEST_PRECEDENCE + 1)
    CorsWebFilter corsWebFilter(@Value("${riskpulse.gateway.cors-allowed-origins}") String origins) {
        CorsConfiguration config = new CorsConfiguration();
        config.setAllowedOrigins(Arrays.stream(origins.split(",")).map(String::trim).filter(s -> !s.isEmpty()).toList());
        config.setAllowedMethods(List.of("GET", "POST", "PUT", "DELETE", "OPTIONS"));
        config.setAllowedHeaders(List.of("Authorization", "Content-Type", "X-Request-Id"));
        config.setExposedHeaders(List.of("X-Request-Id", "Retry-After"));
        config.setAllowCredentials(false);
        config.setMaxAge(3600L);
        UrlBasedCorsConfigurationSource source = new UrlBasedCorsConfigurationSource();
        source.registerCorsConfiguration("/**", config);
        return new CorsWebFilter(source);
    }
}
