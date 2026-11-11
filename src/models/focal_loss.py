import numpy as np

class BinaryFocalLoss:
    def __init__(self, gamma=2.0, alpha=0.75):
        self.gamma = gamma
        self.alpha = alpha

    def objective(self, y_true, y_pred_raw):
        # Sigmoid to convert raw margin (logits) to probability
        p = 1.0 / (1.0 + np.exp(-y_pred_raw))
        p = np.clip(p, 1e-15, 1.0 - 1e-15)
        
        # Binary focal loss gradients and hessians
        # For y = 1: p_t = p, alpha_t = alpha
        # For y = 0: p_t = 1 - p, alpha_t = 1 - alpha
        alpha_t = np.where(y_true == 1, self.alpha, 1.0 - self.alpha)
        p_t = np.where(y_true == 1, p, 1.0 - p)
        
        # First order gradient: dL / d(raw_margin)
        grad = alpha_t * ((1.0 - p_t) ** self.gamma) * (
            self.gamma * p_t * np.log(p_t) + (p - y_true)
        )
        
        # Second order hessian: d^2L / d(raw_margin)^2
        hess = alpha_t * ((1.0 - p_t) ** self.gamma) * p * (1.0 - p) * (
            1.0 + self.gamma * (1.0 - 2.0 * p_t) * np.log(p_t)
        )
        # Ensure positive definite hessian for tree splits
        hess = np.maximum(hess, 1e-6)
        
        return grad, hess

    def custom_eval(self, y_true, y_pred_raw):
        # Custom PR-AUC evaluation metric for XGBoost early stopping
        from sklearn.metrics import average_precision_score
        p = 1.0 / (1.0 + np.exp(-y_pred_raw))
        score = average_precision_score(y_true, p)
        return "pr_auc", score
