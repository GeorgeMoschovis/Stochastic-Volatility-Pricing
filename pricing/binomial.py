"""Cox-Ross-Rubinstein binomial tree for European and American options."""

import numpy as np

from pricing.black_scholes import check_inputs


def crr_price(
    S: float,
    K: float,
    T: float,
    r: float,
    sigma: float,
    q: float = 0.0,
    kind: str = "call",
    n: int = 500,
    american: bool = False,
) -> float:
    r"""Option price on a CRR tree with n steps.

    $\Delta t = T/n$, $u = e^{\sigma\sqrt{\Delta t}}$, $d = 1/u$,
    $p^* = \frac{e^{(r-q)\Delta t} - d}{u - d}$.

    Backward induction: $V = e^{-r\Delta t}\,(p^* V_{up} + (1 - p^*) V_{down})$.
    With american=True each node takes $\max(V, \text{payoff})$.
    """
    check_inputs(S, K, T, sigma, kind)
    if n < 1:
        raise ValueError("n must be at least 1")

    dt = T / n
    u = np.exp(sigma * np.sqrt(dt))
    d = 1 / u
    p = (np.exp((r - q) * dt) - d) / (u - d)
    if not 0 < p < 1:
        raise ValueError("risk-neutral probability outside (0, 1): use more steps")
    discount = np.exp(-r * dt)

    def payoff(prices: np.ndarray) -> np.ndarray:
        if kind == "call":
            return np.maximum(prices - K, 0.0)
        return np.maximum(K - prices, 0.0)

    def node_prices(step: int) -> np.ndarray:
        # node j has had j down moves, so index 0 is the highest price
        j = np.arange(step + 1)
        return S * u ** (step - 2 * j)

    V = payoff(node_prices(n))
    for step in range(n - 1, -1, -1):
        # V[:-1] are the up children, V[1:] the down children
        V = discount * (p * V[:-1] + (1 - p) * V[1:])
        if american:
            V = np.maximum(V, payoff(node_prices(step)))
    return float(V[0])
