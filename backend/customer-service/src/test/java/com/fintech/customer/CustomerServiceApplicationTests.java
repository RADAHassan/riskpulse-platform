package com.fintech.customer;
import com.fintech.customer.TestcontainersConfiguration;
import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.annotation.Import;

@SpringBootTest(properties = {"DB_PASSWORD=test", "INTERNAL_SERVICE_TOKEN=test-token"})
@Import(TestcontainersConfiguration.class)
class CustomerServiceApplicationTests {

    @Test
    void contextLoads() {
    }
}