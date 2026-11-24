package com.riskpulse.transaction;

import static org.assertj.core.api.Assertions.assertThat;

import java.io.ByteArrayInputStream;
import java.nio.charset.StandardCharsets;
import java.util.stream.Collectors;
import java.util.stream.IntStream;
import org.junit.jupiter.api.Test;

class SimulatorTest {

    @Test
    void bundledDemoDataIsLoadedFromTheClasspath() throws Exception {
        Simulator simulator = new Simulator("");
        assertThat(simulator.draw(50, null)).hasSize(50).allSatisfy(s -> assertThat(s.features()).hasSize(28));
    }

    @Test
    void fraudRatioIsHonoured() throws Exception {
        Simulator simulator = new Simulator("");
        assertThat(simulator.draw(200, 1.0)).allMatch(Simulator.Sample::fraud);
        assertThat(simulator.draw(200, 0.0)).noneMatch(Simulator.Sample::fraud);
    }

    @Test
    void malformedRowsAreSkipped() throws Exception {
        String header = "amount," + IntStream.rangeClosed(1, 28).mapToObj(i -> "v" + i).collect(Collectors.joining(",")) + ",is_fraud\n";
        String good = "10.5," + IntStream.rangeClosed(1, 28).mapToObj(i -> "0.1").collect(Collectors.joining(",")) + ",0\n";
        String bad = "1,2,3\n";
        Simulator simulator = new Simulator("");
        simulator.load(new ByteArrayInputStream((header + good + bad).getBytes(StandardCharsets.UTF_8)));
        assertThat(simulator.randomCustomer()).isNotNull();
    }
}
