import java.security.KeyPair;
import java.security.KeyPairGenerator;
import java.util.Base64;

/**
 * Generates an RS256 key pair for the auth-service. Prints two lines:
 *   JWT_PRIVATE_KEY=<base64 of PKCS#8 PEM>
 *   JWT_PUBLIC_KEY=<base64 of X.509 PEM>
 * Usage: java scripts/GenKeys.java
 */
public class GenKeys {

    private static String pem(String type, byte[] der) {
        String body = Base64.getMimeEncoder(64, "\n".getBytes()).encodeToString(der);
        String text = "-----BEGIN " + type + "-----\n" + body + "\n-----END " + type + "-----\n";
        return Base64.getEncoder().encodeToString(text.getBytes());
    }

    public static void main(String[] args) throws Exception {
        KeyPairGenerator generator = KeyPairGenerator.getInstance("RSA");
        generator.initialize(3072);
        KeyPair pair = generator.generateKeyPair();
        System.out.println("JWT_PRIVATE_KEY=" + pem("PRIVATE KEY", pair.getPrivate().getEncoded()));
        System.out.println("JWT_PUBLIC_KEY=" + pem("PUBLIC KEY", pair.getPublic().getEncoded()));
    }
}
