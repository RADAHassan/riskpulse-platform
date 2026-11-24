package com.riskpulse.auth;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import com.riskpulse.auth.security.JwtKeys;
import java.security.KeyPair;
import java.security.KeyPairGenerator;
import java.security.interfaces.RSAPublicKey;
import java.util.Base64;
import org.junit.jupiter.api.Test;
import org.springframework.mock.env.MockEnvironment;

class JwtKeysTest {

    private static String pem(String type, byte[] der) {
        String body = Base64.getMimeEncoder(64, "\n".getBytes()).encodeToString(der);
        String text = "-----BEGIN " + type + "-----\n" + body + "\n-----END " + type + "-----\n";
        return Base64.getEncoder().encodeToString(text.getBytes());
    }

    private static KeyPair pair() throws Exception {
        KeyPairGenerator g = KeyPairGenerator.getInstance("RSA");
        g.initialize(2048);
        return g.generateKeyPair();
    }

    @Test
    void refusesToStartWithoutKeysOutsideDevAndTest() {
        MockEnvironment prod = new MockEnvironment();
        prod.setActiveProfiles("prod");
        assertThatThrownBy(() -> new JwtKeys("", "", "", "k1", prod)).isInstanceOf(IllegalStateException.class);
    }

    @Test
    void generatesAnEphemeralKeyInDev() throws Exception {
        MockEnvironment dev = new MockEnvironment();
        dev.setActiveProfiles("dev");
        assertThat(new JwtKeys("", "", "", "k1", dev).jwks().toString()).contains("k1");
    }

    @Test
    void loadsConfiguredKeyAndPublishesPreviousKeyForRotation() throws Exception {
        KeyPair current = pair();
        KeyPair previous = pair();
        JwtKeys keys = new JwtKeys(pem("PRIVATE KEY", current.getPrivate().getEncoded()),
                pem("PUBLIC KEY", current.getPublic().getEncoded()),
                pem("PUBLIC KEY", previous.getPublic().getEncoded()), "rp-2", new MockEnvironment());
        String jwks = keys.jwks().toString();
        assertThat(jwks).contains("rp-2").contains("rp-2-previous");
        assertThat(keys.signingKey().getKeyID()).isEqualTo("rp-2");
        assertThat(keys.publicKey().getModulus()).isEqualTo(((RSAPublicKey) current.getPublic()).getModulus());
    }
}
