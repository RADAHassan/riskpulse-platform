package com.riskpulse.common.security;

import java.util.Collection;
import java.util.List;
import java.util.stream.Collectors;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.convert.converter.Converter;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configurers.AbstractHttpConfigurer;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.oauth2.core.DelegatingOAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2TokenValidator;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.jwt.JwtDecoder;
import org.springframework.security.oauth2.jwt.JwtValidators;
import org.springframework.security.oauth2.jwt.NimbusJwtDecoder;
import org.springframework.security.oauth2.server.resource.authentication.JwtAuthenticationConverter;
import org.springframework.security.oauth2.server.resource.web.authentication.BearerTokenAuthenticationFilter;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.header.writers.ReferrerPolicyHeaderWriter;

/**
 * Resource-server security shared by every servlet service: stateless bearer JWT (RS256, keys from the
 * auth-service JWKS), role mapping, method security, hardened headers and RFC 7807 security errors.
 */
@Configuration
@EnableMethodSecurity
public class CommonSecurityConfig {

    private static final String[] PUBLIC = {
        "/actuator/health", "/actuator/health/**", "/actuator/prometheus", "/actuator/info",
        "/v3/api-docs", "/v3/api-docs/**", "/swagger-ui.html", "/swagger-ui/**"
    };

    @Bean
    SecurityFilterChain filterChain(
            HttpSecurity http,
            JwtAuthenticationConverter jwtAuthenticationConverter,
            @Value("${riskpulse.security.service-key:}") String serviceKey,
            @Value("${riskpulse.security.public-paths:}") List<String> extraPublicPaths) throws Exception {
        http.csrf(AbstractHttpConfigurer::disable)
                .cors(AbstractHttpConfigurer::disable)
                .sessionManagement(s -> s.sessionCreationPolicy(SessionCreationPolicy.STATELESS))
                .headers(h -> h
                        .contentSecurityPolicy(c -> c.policyDirectives("default-src 'none'; frame-ancestors 'none'"))
                        .frameOptions(f -> f.deny())
                        .contentTypeOptions(Customizer.withDefaults())
                        .referrerPolicy(r -> r.policy(ReferrerPolicyHeaderWriter.ReferrerPolicy.NO_REFERRER))
                        .httpStrictTransportSecurity(hsts -> hsts.includeSubDomains(true).maxAgeInSeconds(31536000)))
                .authorizeHttpRequests(a -> {
                    a.requestMatchers(PUBLIC).permitAll();
                    if (!extraPublicPaths.isEmpty()) {
                        a.requestMatchers(extraPublicPaths.stream().filter(p -> !p.isBlank()).toArray(String[]::new))
                                .permitAll();
                    }
                    a.anyRequest().authenticated();
                })
                .oauth2ResourceServer(o -> o
                        .jwt(j -> j.jwtAuthenticationConverter(jwtAuthenticationConverter))
                        .authenticationEntryPoint((req, res, ex) ->
                                ProblemJson.write(res, 401, "Unauthorized", "Authentication required"))
                        .accessDeniedHandler((req, res, ex) ->
                                ProblemJson.write(res, 403, "Forbidden", "Access denied")))
                .addFilterBefore(new ServiceKeyFilter(serviceKey), BearerTokenAuthenticationFilter.class);
        return http.build();
    }

    @Bean
    JwtAuthenticationConverter jwtAuthenticationConverter() {
        JwtAuthenticationConverter converter = new JwtAuthenticationConverter();
        converter.setJwtGrantedAuthoritiesConverter(rolesConverter());
        return converter;
    }

    static Converter<Jwt, Collection<GrantedAuthority>> rolesConverter() {
        return jwt -> {
            List<String> roles = jwt.getClaimAsStringList(AuthenticatedUser.CLAIM_ROLES);
            if (roles == null) {
                return List.of();
            }
            return roles.stream()
                    .map(r -> (GrantedAuthority) new SimpleGrantedAuthority("ROLE_" + r))
                    .collect(Collectors.toList());
        };
    }

    /** Lazy JWKS-backed decoder: the key set is fetched on first use, then cached. */
    @Bean
    @ConditionalOnMissingBean(JwtDecoder.class)
    JwtDecoder jwtDecoder(
            @Value("${riskpulse.security.jwks-uri}") String jwksUri,
            @Value("${riskpulse.security.issuer:riskpulse-auth}") String issuer) {
        NimbusJwtDecoder decoder = NimbusJwtDecoder.withJwkSetUri(jwksUri).build();
        OAuth2TokenValidator<Jwt> validator = new DelegatingOAuth2TokenValidator<>(JwtValidators.createDefaultWithIssuer(issuer));
        decoder.setJwtValidator(validator);
        return decoder;
    }
}
