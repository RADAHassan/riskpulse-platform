package com.riskpulse.risk;

import static org.assertj.core.api.Assertions.assertThat;

import com.riskpulse.risk.domain.Decision;
import com.riskpulse.risk.ml.DecisionPolicy;
import com.riskpulse.risk.ml.MlResult;
import java.util.List;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.CsvSource;

class DecisionPolicyTest {

    private final DecisionPolicy policy = new DecisionPolicy(0.25);

    private static MlResult ml(String decision, double unc, List<String> set, boolean review) {
        return new MlResult(1, 0.9, unc, decision, set, review, "none", "v", "3");
    }

    @Test
    void noModelAnswerFallsBackToHumanReviewNeverApprove() {
        DecisionPolicy.Outcome o = policy.decide(null);
        assertThat(o.decision()).isEqualTo(Decision.HUMAN_REVIEW);
        assertThat(o.fallback()).isTrue();
    }

    @Test
    void confidentFraudIsDeclined() {
        assertThat(policy.decide(ml("DECLINE", 0.05, List.of("FRAUD"), false)).decision()).isEqualTo(Decision.DECLINE);
    }

    @ParameterizedTest
    @CsvSource({"0.25", "0.40", "0.90"})
    void highUncertaintyIsNeverDeclined(double uncertainty) {
        DecisionPolicy.Outcome o = policy.decide(ml("DECLINE", uncertainty, List.of("FRAUD"), false));
        assertThat(o.decision()).isEqualTo(Decision.HUMAN_REVIEW);
        assertThat(o.reason()).isEqualTo("uncertain_prediction_not_auto_declined");
    }

    @Test
    void nonSingletonConformalSetIsNeverDeclined() {
        assertThat(policy.decide(ml("DECLINE", 0.01, List.of("LEGIT", "FRAUD"), false)).decision())
                .isEqualTo(Decision.HUMAN_REVIEW);
        assertThat(policy.decide(ml("DECLINE", 0.01, List.of(), false)).decision()).isEqualTo(Decision.HUMAN_REVIEW);
        assertThat(policy.decide(ml("DECLINE", 0.01, null, false)).decision()).isEqualTo(Decision.HUMAN_REVIEW);
        assertThat(policy.decide(ml("DECLINE", 0.01, List.of("LEGIT"), false)).decision()).isEqualTo(Decision.HUMAN_REVIEW);
    }

    @Test
    void modelReviewRequestIsHonoured() {
        assertThat(policy.decide(ml("HUMAN_REVIEW", 0.4, List.of("LEGIT", "FRAUD"), true)).decision())
                .isEqualTo(Decision.HUMAN_REVIEW);
    }

    @Test
    void approveIsOnlyGrantedWhenRouterDoesNotFlag() {
        assertThat(policy.decide(ml("APPROVE", 0.0, List.of("LEGIT"), false)).decision()).isEqualTo(Decision.APPROVE);
        assertThat(policy.decide(ml("APPROVE", 0.0, List.of("LEGIT"), true)).decision()).isEqualTo(Decision.HUMAN_REVIEW);
    }

    @Test
    void unknownDecisionsAreNotApproved() {
        assertThat(policy.decide(ml("MAYBE", 0.0, List.of("LEGIT"), false)).decision()).isEqualTo(Decision.HUMAN_REVIEW);
        assertThat(policy.decide(ml(null, 0.0, List.of("LEGIT"), false)).decision()).isEqualTo(Decision.HUMAN_REVIEW);
    }
}
