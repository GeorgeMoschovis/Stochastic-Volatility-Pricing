# Learning guide

How to read this project so that you can explain every line of it. Read the files in the order below: each one uses only what came before. For every file, read the matching section of the documentation (`docs/index.html`) first, then the code, then its tests.

Hull chapter and section numbers refer to *Options, Futures, and Other Derivatives*, 10th edition. They can shift slightly in other editions.

## Reading order

| # | File | What it teaches | Hull | Tests |
|---|---|---|---|---|
| 1 | `pricing/black_scholes.py` | The closed-form price, put–call parity, the five Greeks, and how to write formulas that work on arrays | Ch. 15 (Black–Scholes–Merton, section 15.8 for the formula and the S = 42, K = 40 example), Ch. 17 (dividend yield q), Ch. 19 (Greeks) | `test_black_scholes.py` |
| 2 | `pricing/binomial.py` | Risk-neutral probability, backward induction, early exercise | Ch. 13 (binomial trees), Ch. 21 sections 21.1 to 21.2 (trees as a numerical method) | `test_binomial.py` |
| 3 | `pricing/monte_carlo.py` | Pricing as an average, standard errors, confidence intervals, antithetic and control variates | Ch. 21 sections 21.6 (Monte Carlo) and 21.7 (variance reduction) | `test_monte_carlo.py` |
| 4 | `pricing/greeks.py` | Finite differences, the bump-size trade-off, common random numbers | Ch. 19; Ch. 21 section 21.6 (Greeks by simulation) | `test_greeks.py` |
| 5 | `pricing/implied_vol.py` | Root finding, no-arbitrage bounds, why a vectorised solver matters | Ch. 11 (bounds on option prices), Ch. 15 section 15.11 (implied volatilities) | `test_implied_vol.py` |
| 6 | `pricing/convergence.py` | How to measure a numerical method: error against work, log-log plots, efficiency | Ch. 21 | `test_convergence.py` |
| 7 | `pricing/heston.py` | Stochastic volatility, characteristic functions, pricing by Fourier inversion, an SDE discretisation | Ch. 27 section 27.2 (stochastic volatility models); Heston (1993); Gatheral Ch. 2 | `test_heston.py` |
| 8 | `data/fetch_options.py` | What real option data looks like and how to clean it; the forward from put–call parity | Ch. 11 (put–call parity), Ch. 20 (volatility smiles) | `test_data.py` |
| 9 | `pricing/calibration.py` | Calibration as a least-squares problem, bounds, initial guesses, benchmarks | Ch. 20, Ch. 27; Gatheral Ch. 3 | `test_calibration.py` |
| 10 | `api/schemas.py`, `api/main.py` | Turning a library into a validated JSON API | | `test_api.py` |
| 11 | `web/js/api.js`, `ui.js`, `app.js`, then one file per tab | A front end without a framework: fetch, state, Plotly charts | | checked in the browser |

Glasserman, *Monte Carlo Methods in Financial Engineering*, is the reference for files 3, 4 and 6: Ch. 1 (foundations), Ch. 4 (variance reduction), Ch. 7 (estimating sensitivities).

## Questions you should be able to answer

Black–Scholes and the tree
1. Why does the stock's expected return not appear in the option price?
2. What do N(d₁) and N(d₂) mean?
3. Why does the tree price oscillate as n goes from even to odd?
4. Why is the American call equal to the European call here, while the puts differ?

Monte Carlo and Greeks
5. Why does the standard error fall like N^(-1/2), and what does a 95% interval promise?
6. Why does the control variate reduce variance, and what determines by how much?
7. Why must the bumped Monte Carlo prices use the same seed?
8. Why does the gamma of a tree price come out as zero with a 0.1% bump?

Heston and calibration
9. What does each of the five parameters do to the surface? (Check your answers against the five small charts in the documentation.)
10. What is the "little Heston trap", and what would go wrong without it?
11. Why is the integration limit not a fixed number?
12. Why are out-of-the-money options used, and why are errors measured in implied volatility rather than in price?
13. The Feller condition is violated in the fit. What does that mean, and does it invalidate the prices?
14. Why is "one flat volatility per maturity" a fair benchmark?

## Experiments that take five minutes

- In the Pricer tab, switch the finite differences to the binomial tree and move the spot bump between 0.1%, 1% and 5%. Watch gamma.
- Change the seed and watch the dots move in the interval chart while the bar lengths stay put.
- Set the option to a put and compare the tree's American and European prices. Then set r = 0 and see the premium vanish.
- In the Volatility tab, switch the height to total variance. It should rise from front to back for every strike.
- In `tests/test_calibration.py`, change the true parameters of the synthetic test and check that they are still recovered.

## Three exercises to extend the project

### 1. American options by Monte Carlo (Longstaff–Schwartz)

The tree prices American options but Monte Carlo does not. Add `pricing/lsm.py`.

- Simulate full paths of geometric Brownian motion on m exercise dates.
- Work backwards: at each date, regress the discounted future cash flow on basis functions of the stock price (1, S, S²), using in-the-money paths only, and exercise where the payoff exceeds the fitted continuation value.
- Check: Hull's put with n = 500 steps on the tree is worth 0.9103 with American exercise and 0.8085 European. Your estimate should approach 0.91 from below as m grows.
- Reading: Longstaff and Schwartz (2001); Glasserman Ch. 8; Hull Ch. 27 (Monte Carlo simulation and American options).

### 2. FFT pricing (Carr–Madan)

`heston_call_strikes` already prices many strikes at once. The fast Fourier transform prices a whole grid of strikes in one pass.

- Reuse `heston_cf`. Implement the damped call transform of Carr and Madan (1999) and evaluate it with `numpy.fft`.
- Check: agree with `heston_price` to 1e-6 on the strikes of the test in `tests/test_heston.py`.
- Then measure: for how many strikes is the FFT faster than the Gauss–Legendre grid? Is it still accurate for a two-week maturity?
- Reading: Carr and Madan (1999), "Option valuation using the fast Fourier transform".

### 3. A local-volatility comparison (Dupire)

Heston is one way to fit a smile. Local volatility is another: σ becomes a function of spot and time, chosen to fit the surface exactly.

- Use the calibrated Heston surface as a smooth, arbitrage-free input. Compute Dupire's local variance from total variance w(k, T) with finite differences (the formula in terms of w is in Gatheral Ch. 1).
- Price a European option with that local volatility by Monte Carlo and check that it reproduces the Heston price.
- Then compare something the two models disagree on: the implied-volatility smile one year forward, or the price of a barrier option.
- Reading: Dupire (1994); Gatheral Ch. 1; Hull Ch. 27 (the implied volatility function model).

## Smaller ideas

- Richardson extrapolation or averaging n and n + 1 to remove the tree's oscillation.
- Quasi-random (Sobol) numbers in `monte_carlo.py`, and a new line in the convergence chart.
- Vega weights or bid-ask-spread weights in `calibrate_heston` (the `weights` argument is already there).
- Calibrate on several days and plot how the parameters move.
- Add jumps (Bates model): only `heston_cf` changes.
