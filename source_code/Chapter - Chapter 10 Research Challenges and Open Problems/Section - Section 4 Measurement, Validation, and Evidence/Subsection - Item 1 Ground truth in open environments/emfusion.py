import numpy as np

def em_fuse(labels_matrix, max_iter=200, tol=1e-6, eps=1e-9):
    """
    labels_matrix: (T, I) binary array where rows are time steps.
    Returns: posteriors p_y (T,), reliabilities r (I,)
    """
    T, I = labels_matrix.shape
    # initialize reliabilities with slight bias to avoid degenerate values
    r = np.clip(np.mean(labels_matrix, axis=0), 0.01, 0.99)
    # prior for positive event (can be estimated or set from domain)
    p_prior = np.clip(np.mean(labels_matrix), 0.01, 0.99)

    p_y = np.full(T, p_prior)
    for iteration in range(max_iter):
        r_old = r.copy()
        # E-step: compute P(y=1 | x) using Bayes, assume independence
        log_p_x_given_y1 = np.sum(labels_matrix * np.log(r + eps) +
                                  (1 - labels_matrix) * np.log(1 - r + eps), axis=1)
        log_p_x_given_y0 = np.sum(labels_matrix * np.log(1 - r + eps) +
                                  (1 - labels_matrix) * np.log(r + eps), axis=1)
        # use log-sum-exp for numerical stability
        a = log_p_x_given_y1 + np.log(p_prior + eps)
        b = log_p_x_given_y0 + np.log(1 - p_prior + eps)
        maxab = np.maximum(a, b)
        denom = np.exp(a - maxab) + np.exp(b - maxab)
        p_y = np.exp(a - maxab) / (denom + eps)

        # M-step: update reliabilities r_i
        # expected agreement between sensor i and latent y
        r = (p_y * labels_matrix + (1 - p_y) * (1 - labels_matrix)).sum(axis=0) / T
        r = np.clip(r, 0.001, 0.999)  # numerical safety
        # optional: update prior
        p_prior = p_y.mean()

        if np.max(np.abs(r - r_old)) < tol:
            break
    return p_y, r