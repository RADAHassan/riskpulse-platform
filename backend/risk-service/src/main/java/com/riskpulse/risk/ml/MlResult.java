package com.riskpulse.risk.ml;

import com.fasterxml.jackson.annotation.JsonIgnoreProperties;
import com.fasterxml.jackson.annotation.JsonProperty;
import java.util.List;

/** Response of ml-serving {@code POST /predict} (see docs/contracts/predict-response.schema.json). */
@JsonIgnoreProperties(ignoreUnknown = true)
public record MlResult(
        int prediction,
        double probability,
        double uncertainty,
        String decision,
        @JsonProperty("conformal_set") List<String> conformalSet,
        @JsonProperty("human_review") boolean humanReview,
        @JsonProperty("review_reason") String reviewReason,
        @JsonProperty("model_version") String modelVersion,
        @JsonProperty("registry_version") String registryVersion) {
}
