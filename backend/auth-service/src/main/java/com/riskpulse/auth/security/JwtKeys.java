package com.riskpulse.auth.security;

import com.nimbusds.jose.jwk.JWK;
import com.nimbusds.jose.jwk.JWKSet;
import com.nimbusds.jose.jwk.RSAKey;
import java.io.ByteArrayInputStream;
import java.security.KeyPair;
import java.security.KeyPairGenerator;
import java.security.interfaces.RSAPrivateKey;
import java.security.interfaces.RSAPublicKey;
import java.util.ArrayList;
import java.util.Base64;
import java.util.List;
import java.util.Map;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.core.env.Environment;
import org.springframework.core.env.Profiles;
import org.springframework.security.converter.RsaKeyConverters;
import org.springframework.stereotype.Component;

/**
 * Signing-key management (RS256).
 *
 * <p>Production: {@code JWT_PRIVATE_KEY} / {@code JWT_PUBLIC_KEY} (base64 of PEM, from a Kubernetes Secret).
 * Rotation: deploy the new pair as current and the old public key as {@code JWT_PREVIOUS_PUBLIC_KEY}; the JWKS
 * publishes both until the old access tokens (15 min) and refresh tokens are gone, then drop the previous key.
 * Only profiles {@code dev} / {@code test} may start without a configured key (ephemeral pair).
 */
@Component
public class JwtKeys {

    private static final Logger LOG = LoggerFactory.getLogger(JwtKeys.class);

    private final RSAKey signing;
    private final List<RSAKey> published = new ArrayList<>();

    public JwtKeys(
            @Value("${riskpulse.jwt.private-key:}") String privateKey,
            @Value("${riskpulse.jwt.public-key:}") String publicKey,
            @Value("${riskpulse.jwt.previous-public-key:}") String previousPublicKey,
            @Value("${riskpulse.jwt.key-id:rp-1}") String keyId,
            Environment env) throws Exception {
        RSAPublicKey pub;
        RSAPrivateKey priv;
        if (!privateKey.isBlank() && !publicKey.isBlank()) {
            priv = RsaKeyConverters.pkcs8().convert(new ByteArrayInputStream(Base64.getDecoder().decode(privateKey.trim())));
            pub = RsaKeyConverters.x509().convert(new ByteArrayInputStream(Base64.getDecoder().decode(publicKey.trim())));
        } else if (env.acceptsProfiles(Profiles.of("dev", "test"))) {
            LOG.warn("No JWT key configured: generating an EPHEMERAL RSA key pair (dev/test profile only)");
            KeyPairGenerator gen = KeyPairGenerator.getInstance("RSA");
            gen.initialize(2048);
            KeyPair pair = gen.generateKeyPair();
            priv = (RSAPrivateKey) pair.getPrivate();
            pub = (RSAPublicKey) pair.getPublic();
        } else {
            throw new IllegalStateException("JWT_PRIVATE_KEY and JWT_PUBLIC_KEY are required outside dev/test profiles");
        }
        this.signing = new RSAKey.Builder(pub).privateKey(priv).keyID(keyId).build();
        published.add(signing.toPublicJWK());
        if (!previousPublicKey.isBlank()) {
            RSAPublicKey previous = RsaKeyConverters.x509()
                    .convert(new ByteArrayInputStream(Base64.getDecoder().decode(previousPublicKey.trim())));
            published.add(new RSAKey.Builder(previous).keyID(keyId + "-previous").build());
        }
    }

    public RSAKey signingKey() {
        return signing;
    }

    public RSAPublicKey publicKey() throws Exception {
        return signing.toRSAPublicKey();
    }

    /** Public JWKS document (never contains private material). */
    public Map<String, Object> jwks() {
        return new JWKSet(new ArrayList<JWK>(published)).toJSONObject();
    }
}
