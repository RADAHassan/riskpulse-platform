package com.riskpulse.auth.web;

import com.riskpulse.auth.domain.UserAccount;
import com.riskpulse.auth.security.JwtKeys;
import com.riskpulse.auth.service.AuthService;
import com.riskpulse.common.security.AuthenticatedUser;
import jakarta.validation.Valid;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Pattern;
import jakarta.validation.constraints.Size;
import java.util.Map;
import java.util.UUID;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.ResponseStatus;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class AuthController {

    public record LoginRequest(@NotBlank @Size(max = 100) String username, @NotBlank @Size(max = 128) String password) {
    }

    public record RefreshRequest(@NotBlank @Size(max = 200) String refreshToken) {
    }

    public record TokenResponse(String accessToken, String refreshToken, String tokenType, long expiresIn,
                                String username, String role, UUID customerId) {
    }

    public record CreateUserRequest(
            @NotBlank @Size(min = 3, max = 100) @Pattern(regexp = "^[A-Za-z0-9._@-]+$") String username,
            @NotBlank @Size(min = 12, max = 128) String password,
            @NotNull UserAccount.Role role,
            UUID customerId) {
    }

    public record UserResponse(UUID id, String username, String role, UUID customerId) {
    }

    private final AuthService auth;
    private final JwtKeys keys;

    public AuthController(AuthService auth, JwtKeys keys) {
        this.auth = auth;
        this.keys = keys;
    }

    @PostMapping("/api/auth/login")
    public TokenResponse login(@Valid @RequestBody LoginRequest request) {
        return toResponse(auth.login(request.username(), request.password()));
    }

    @PostMapping("/api/auth/refresh")
    public TokenResponse refresh(@Valid @RequestBody RefreshRequest request) {
        return toResponse(auth.refresh(request.refreshToken()));
    }

    @PostMapping("/api/auth/logout")
    @ResponseStatus(HttpStatus.NO_CONTENT)
    public void logout(@Valid @RequestBody RefreshRequest request) {
        auth.logout(request.refreshToken());
    }

    @GetMapping("/api/auth/me")
    public Map<String, Object> me(Authentication authentication) {
        AuthenticatedUser user = AuthenticatedUser.from(authentication);
        return Map.of("id", user.userId(), "username", String.valueOf(user.username()), "role", user.role(),
                "customerId", String.valueOf(user.customerId()));
    }

    @PostMapping("/api/auth/users")
    @PreAuthorize("hasRole('ADMIN')")
    public ResponseEntity<UserResponse> createUser(@Valid @RequestBody CreateUserRequest request,
                                                   Authentication authentication) {
        AuthenticatedUser caller = AuthenticatedUser.from(authentication);
        UserAccount created = auth.createUser(String.valueOf(caller.username()), request.username(), request.password(),
                request.role(), request.customerId());
        return ResponseEntity.status(HttpStatus.CREATED).body(new UserResponse(created.getId(), created.getUsername(),
                created.getRole().name(), created.getCustomerId()));
    }

    /** Public key set used by the gateway and every resource server to validate tokens. */
    @RequestMapping(path = "/.well-known/jwks.json", method = org.springframework.web.bind.annotation.RequestMethod.GET)
    public Map<String, Object> jwks() {
        return keys.jwks();
    }

    private static TokenResponse toResponse(AuthService.Tokens t) {
        return new TokenResponse(t.accessToken(), t.refreshToken(), "Bearer", t.expiresIn(), t.user().getUsername(),
                t.user().getRole().name(), t.user().getCustomerId());
    }
}
