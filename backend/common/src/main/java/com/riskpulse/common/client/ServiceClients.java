package com.riskpulse.common.client;

import com.riskpulse.common.security.ServiceKeyFilter;
import com.riskpulse.common.web.RequestIdFilter;
import java.net.http.HttpClient;
import java.time.Duration;
import org.slf4j.MDC;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.http.HttpHeaders;
import org.springframework.http.client.JdkClientHttpRequestFactory;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.security.oauth2.server.resource.authentication.JwtAuthenticationToken;
import org.springframework.stereotype.Component;
import org.springframework.web.client.RestClient;

/**
 * Builds {@link RestClient}s for service-to-service calls. Every outbound call carries the shared service key,
 * the correlation id and — when there is an authenticated caller — the propagated JWT, so that the callee
 * re-validates identity and applies its own authorisation rules.
 */
@Component
public class ServiceClients {

    private final String serviceKey;

    public ServiceClients(@Value("${riskpulse.security.service-key:}") String serviceKey) {
        this.serviceKey = serviceKey;
    }

    public RestClient create(String baseUrl, Duration connectTimeout, Duration readTimeout) {
        HttpClient jdk = HttpClient.newBuilder().connectTimeout(connectTimeout).build();
        JdkClientHttpRequestFactory factory = new JdkClientHttpRequestFactory(jdk);
        factory.setReadTimeout(readTimeout);
        return RestClient.builder()
                .baseUrl(baseUrl)
                .requestFactory(factory)
                .requestInterceptor((request, body, execution) -> {
                    request.getHeaders().set(ServiceKeyFilter.HEADER, serviceKey);
                    String requestId = MDC.get(RequestIdFilter.MDC_KEY);
                    if (requestId != null) {
                        request.getHeaders().set(RequestIdFilter.HEADER, requestId);
                    }
                    Authentication auth = SecurityContextHolder.getContext().getAuthentication();
                    if (auth instanceof JwtAuthenticationToken jwt && !request.getHeaders().containsHeader(HttpHeaders.AUTHORIZATION)) {
                        request.getHeaders().setBearerAuth(jwt.getToken().getTokenValue());
                    }
                    return execution.execute(request, body);
                })
                .build();
    }
}
