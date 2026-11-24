package com.riskpulse.auth.service;

import com.riskpulse.auth.domain.RefreshToken;
import com.riskpulse.auth.domain.RefreshTokenRepository;
import com.riskpulse.auth.domain.UserAccount;
import com.riskpulse.auth.domain.UserRepository;
import com.riskpulse.auth.security.TokenService;
import com.riskpulse.common.audit.AuditClient;
import com.riskpulse.common.audit.AuditEvent;
import com.riskpulse.common.logging.Masking;
import com.riskpulse.common.web.ApiException;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.security.SecureRandom;
import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.util.Base64;
import java.util.HexFormat;
import java.util.Map;
import java.util.UUID;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.http.HttpStatus;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class AuthService {

    private static final Logger LOG = LoggerFactory.getLogger(AuthService.class);
    private static final SecureRandom RANDOM = new SecureRandom();

    public record Tokens(String accessToken, String refreshToken, long expiresIn, UserAccount user) {
    }

    private final UserRepository users;
    private final RefreshTokenRepository refreshTokens;
    private final PasswordEncoder encoder;
    private final TokenService tokens;
    private final AuditClient audit;
    private final Clock clock;
    private final int maxFailures;
    private final Duration lockDuration;
    private final Duration refreshTtl;
    private final String dummyHash;

    public AuthService(UserRepository users, RefreshTokenRepository refreshTokens, PasswordEncoder encoder,
                       TokenService tokens, AuditClient audit, Clock clock,
                       @Value("${riskpulse.auth.max-failures:5}") int maxFailures,
                       @Value("${riskpulse.auth.lock-minutes:15}") long lockMinutes,
                       @Value("${riskpulse.jwt.refresh-ttl:P7D}") Duration refreshTtl) {
        this.users = users;
        this.refreshTokens = refreshTokens;
        this.encoder = encoder;
        this.tokens = tokens;
        this.audit = audit;
        this.clock = clock;
        this.maxFailures = maxFailures;
        this.lockDuration = Duration.ofMinutes(lockMinutes);
        this.refreshTtl = refreshTtl;
        this.dummyHash = encoder.encode("timing-equaliser-" + UUID.randomUUID());
    }

    @Transactional(noRollbackFor = ApiException.class)
    public Tokens login(String username, String password) {
        Instant now = clock.instant();
        UserAccount user = users.findByUsernameIgnoreCase(username).orElse(null);
        if (user == null) {
            encoder.matches(password, dummyHash); // equalise timing: no user enumeration
            audit.record(AuditEvent.of(Masking.sanitize(username), "ANONYMOUS", "LOGIN_FAILURE", "User", "unknown"));
            throw new ApiException(HttpStatus.UNAUTHORIZED, "Invalid credentials");
        }
        if (user.isLocked(now)) {
            audit.record(AuditEvent.of(user.getUsername(), user.getRole().name(), "LOGIN_BLOCKED_LOCKED", "User",
                    user.getId().toString()));
            throw new ApiException(HttpStatus.LOCKED, "Account temporarily locked after repeated failures");
        }
        if (!user.isEnabled() || !encoder.matches(password, user.getPasswordHash())) {
            boolean locked = user.registerFailure(maxFailures, now.plus(lockDuration));
            users.save(user);
            audit.record(AuditEvent.of(user.getUsername(), user.getRole().name(),
                    locked ? "ACCOUNT_LOCKED" : "LOGIN_FAILURE", "User", user.getId().toString()));
            if (locked) {
                LOG.warn("Account {} locked after {} failed attempts", Masking.id(user.getId()), maxFailures);
            }
            throw new ApiException(HttpStatus.UNAUTHORIZED, "Invalid credentials");
        }
        user.registerSuccess();
        users.save(user);
        audit.record(AuditEvent.of(user.getUsername(), user.getRole().name(), "LOGIN_SUCCESS", "User",
                user.getId().toString()));
        return issue(user, now);
    }

    @Transactional(noRollbackFor = ApiException.class)
    public Tokens refresh(String presentedToken) {
        Instant now = clock.instant();
        RefreshToken stored = refreshTokens.findByTokenHash(hash(presentedToken))
                .orElseThrow(() -> new ApiException(HttpStatus.UNAUTHORIZED, "Invalid refresh token"));
        if (stored.isRevoked()) {
            // A rotated token is being replayed: assume theft and kill every session of the user.
            refreshTokens.revokeAllForUser(stored.getUserId(), now);
            audit.record(AuditEvent.of("unknown", "ANONYMOUS", "REFRESH_TOKEN_REUSE_DETECTED", "User",
                    stored.getUserId().toString()));
            throw new ApiException(HttpStatus.UNAUTHORIZED, "Invalid refresh token");
        }
        if (stored.isExpired(now)) {
            throw new ApiException(HttpStatus.UNAUTHORIZED, "Refresh token expired");
        }
        UserAccount user = users.findById(stored.getUserId())
                .filter(UserAccount::isEnabled)
                .orElseThrow(() -> new ApiException(HttpStatus.UNAUTHORIZED, "Invalid refresh token"));
        stored.revoke(now);
        refreshTokens.save(stored);
        audit.record(AuditEvent.of(user.getUsername(), user.getRole().name(), "TOKEN_REFRESHED", "User",
                user.getId().toString()));
        return issue(user, now);
    }

    @Transactional
    public void logout(String presentedToken) {
        refreshTokens.findByTokenHash(hash(presentedToken)).ifPresent(t -> {
            t.revoke(clock.instant());
            refreshTokens.save(t);
        });
    }

    @Transactional
    public UserAccount createUser(String actor, String username, String rawPassword, UserAccount.Role role, UUID customerId) {
        if (users.existsByUsernameIgnoreCase(username)) {
            throw ApiException.conflict("Username already exists");
        }
        if (role == UserAccount.Role.CUSTOMER && customerId == null) {
            throw ApiException.badRequest("customerId is required for the CUSTOMER role");
        }
        UserAccount created = users.save(new UserAccount(username, encoder.encode(rawPassword), role,
                role == UserAccount.Role.CUSTOMER ? customerId : null));
        audit.record(AuditEvent.of(actor, "ADMIN", "USER_CREATED", "User", created.getId().toString())
                .withDetails(Map.of("role", role.name())));
        return created;
    }

    private Tokens issue(UserAccount user, Instant now) {
        byte[] raw = new byte[32];
        RANDOM.nextBytes(raw);
        String refresh = Base64.getUrlEncoder().withoutPadding().encodeToString(raw);
        refreshTokens.save(new RefreshToken(user.getId(), hash(refresh), now.plus(refreshTtl)));
        return new Tokens(tokens.issueAccessToken(user, now), refresh, tokens.accessTtlSeconds(), user);
    }

    static String hash(String token) {
        try {
            return HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256").digest(token.getBytes(StandardCharsets.UTF_8)));
        } catch (NoSuchAlgorithmException e) {
            throw new IllegalStateException(e);
        }
    }
}
