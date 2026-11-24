package com.riskpulse.auth.seed;

import com.riskpulse.auth.domain.UserAccount;
import com.riskpulse.auth.domain.UserRepository;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.stereotype.Component;

/**
 * Seeds one ADMIN and one ANALYST. Passwords come from the environment (Kubernetes Secret);
 * there is no default password: an account whose password variable is empty is simply not created.
 */
@Component
public class SeedRunner implements ApplicationRunner {

    private static final Logger LOG = LoggerFactory.getLogger(SeedRunner.class);

    private final UserRepository users;
    private final PasswordEncoder encoder;
    private final String adminUser;
    private final String adminPassword;
    private final String analystUser;
    private final String analystPassword;

    public SeedRunner(UserRepository users, PasswordEncoder encoder,
                      @Value("${riskpulse.auth.seed.admin-username}") String adminUser,
                      @Value("${riskpulse.auth.seed.admin-password:}") String adminPassword,
                      @Value("${riskpulse.auth.seed.analyst-username}") String analystUser,
                      @Value("${riskpulse.auth.seed.analyst-password:}") String analystPassword) {
        this.users = users;
        this.encoder = encoder;
        this.adminUser = adminUser;
        this.adminPassword = adminPassword;
        this.analystUser = analystUser;
        this.analystPassword = analystPassword;
    }

    @Override
    public void run(ApplicationArguments args) {
        seed(adminUser, adminPassword, UserAccount.Role.ADMIN);
        seed(analystUser, analystPassword, UserAccount.Role.ANALYST);
    }

    private void seed(String username, String password, UserAccount.Role role) {
        if (password == null || password.isBlank()) {
            LOG.info("No password provided for seed {} account: skipped", role);
            return;
        }
        if (password.length() < 12) {
            throw new IllegalStateException("Seed password for " + role + " must be at least 12 characters");
        }
        if (users.existsByUsernameIgnoreCase(username)) {
            return;
        }
        users.save(new UserAccount(username, encoder.encode(password), role, null));
        LOG.info("Seeded {} account '{}'", role, username);
    }
}
