package com.riskpulse.auth.security;

import com.nimbusds.jose.jwk.JWKSet;
import com.nimbusds.jose.jwk.source.ImmutableJWKSet;
import com.riskpulse.auth.domain.UserAccount;
import java.time.Duration;
import java.time.Instant;
import java.util.List;
import java.util.UUID;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.security.oauth2.jose.jws.SignatureAlgorithm;
import org.springframework.security.oauth2.jwt.JwsHeader;
import org.springframework.security.oauth2.jwt.JwtClaimsSet;
import org.springframework.security.oauth2.jwt.JwtEncoder;
import org.springframework.security.oauth2.jwt.JwtEncoderParameters;
import org.springframework.security.oauth2.jwt.NimbusJwtEncoder;
import org.springframework.stereotype.Service;

/** Issues short-lived RS256 access tokens (default 15 min). */
@Service
public class TokenService {

    private final JwtEncoder encoder;
    private final String issuer;
    private final String keyId;
    private final Duration accessTtl;

    public TokenService(JwtKeys keys,
                        @Value("${riskpulse.security.issuer:riskpulse-auth}") String issuer,
                        @Value("${riskpulse.jwt.access-ttl:PT15M}") Duration accessTtl) {
        this.encoder = new NimbusJwtEncoder(new ImmutableJWKSet<>(new JWKSet(keys.signingKey())));
        this.issuer = issuer;
        this.keyId = keys.signingKey().getKeyID();
        this.accessTtl = accessTtl;
    }

    public String issueAccessToken(UserAccount user, Instant now) {
        JwtClaimsSet.Builder claims = JwtClaimsSet.builder()
                .issuer(issuer)
                .subject(user.getId().toString())
                .issuedAt(now)
                .expiresAt(now.plus(accessTtl))
                .id(UUID.randomUUID().toString())
                .claim("username", user.getUsername())
                .claim("roles", List.of(user.getRole().name()));
        if (user.getCustomerId() != null) {
            claims.claim("customer_id", user.getCustomerId().toString());
        }
        JwsHeader header = JwsHeader.with(SignatureAlgorithm.RS256).keyId(keyId).build();
        return encoder.encode(JwtEncoderParameters.from(header, claims.build())).getTokenValue();
    }

    public long accessTtlSeconds() {
        return accessTtl.toSeconds();
    }
}
