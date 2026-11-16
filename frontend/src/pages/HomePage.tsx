import { useId, useRef, useState } from "react";
import { Link } from "react-router-dom";
import AiAccess from "../components/AiAccess";
import "./home.css";

const FEATURES = [
  {
    id: "predictions", name: "Predictions", kicker: "THE RANGE, NOT JUST A TARGET",
    title: "Put a probability behind your price target.",
    description: "Options prices contain the market's expectations of future moves. Explore the implied distribution to see the upside, the downside, and the uncertainty between them.",
    points: ["Set an observation window and a target date.", "Inspect probability ranges, volatility smiles, and Greeks.", "Choose a past target to compare with the actual stock price."],
    image: "prediction-charts.jpg", alt: "Actual SPY prediction charts showing a shaded price distribution and cumulative price probabilities.",
    caption: "SPY example using observations through August 25, 2026. Historical screenshot, not live prices.",
    link: "/app/predictions", action: "Explore Predictions",
  },
  {
    id: "theta", name: "Theta Plays", kicker: "A SHORTLIST WITH THE EVIDENCE",
    title: "Find volatility premiums worth investigating.",
    description: "Compare implied volatility with historical volatility across saved expiry scans. Separate rich calls from rich puts, then look beyond the ratio before deciding what deserves more research.",
    points: ["Compare overall richness, calls, and puts.", "Sort candidates and inspect their quote provenance.", "See freshness warnings and why a candidate passes or fails quality checks."],
    image: "theta-plays.jpg", alt: "Actual Theta Plays dashboard with expiry selection, volatility ratios, quality flags, and a ranked ticker table.",
    caption: "Saved scan with flagged candidates included for inspection. IV/HV is volatility richness, not a dollar premium or a promise of profit.",
    link: "/app/theta-plays", action: "Explore Theta Plays",
  },
  {
    id: "dacey", name: "Dacey", kicker: "ASK A QUESTION. FOLLOW THE DATA.",
    title: "Research in your own words.",
    description: "Ask Dacey to run a prediction, compare tickers, or inspect Theta candidates. The assistant can use the dashboard's research tools and show the tool results behind its answer.",
    points: ["Ask about probabilities, downside risk, or a past forecast.", "Compare candidates without hopping between views.", "Add sourced Market Context to an observation period."],
    image: "dacey.jpg", alt: "Dacey's actual chat panel with suggested stock research questions and the message input.",
    caption: "The assistant's starting view. Dacey and Market Context require Google sign-in and have usage limits.",
    link: "/app/predictions", action: "Open the research dashboard",
  },
];

export default function HomePage() {
  const [selected, setSelected] = useState(0);
  const [zoomed, setZoomed] = useState(false);
  const imageDialog = useRef<HTMLDialogElement>(null);
  const id = useId();
  const feature = FEATURES[selected];

  const selectTab = (index: number) => {
    setSelected(index);
    document.getElementById(`${id}-tab-${index}`)?.focus();
  };

  return <div className="home-page">
    <a className="home-skip" href="#home-main">Skip to content</a>
    <header className="home-header">
      <Link to="/" className="home-wordmark" aria-label="Decay And Conquer home">Decay <span>And Conquer</span></Link>
      <nav aria-label="Home navigation">
        <a href="#research">Features</a>
        <a href="#method">How it works</a>
        <Link to="/app/predictions">Dashboard</Link>
      </nav>
      <AiAccess label="Sign in with Google" className="home-sign-in" redirectTo="/app/predictions" />
    </header>

    <main id="home-main">
      <section className="home-hero" aria-labelledby="home-title">
        <img className="home-hero-image" src="/screenshots/probability-curve.png" alt="" fetchPriority="high" />
        <div className="home-hero-content">
          <p className="home-eyebrow">OPTIONS PRICES. A DIFFERENT PERSPECTIVE.</p>
          <h1 id="home-title">Decay And Conquer</h1>
          <p className="home-intro">Turn options prices into a clearer view of<br className="home-desktop-break" /> risk, probability, and opportunity.</p>
          <div className="home-actions">
            <Link className="home-primary" to="/app/predictions">Explore the dashboard <span aria-hidden="true">&rarr;</span></Link>
            <a className="home-text-link" href="#research">See it in action <span aria-hidden="true">&darr;</span></a>
          </div>
          <p className="home-access-note">Explore without an account. Sign in for Dacey &amp; Market Context.</p>
        </div>
        <p className="home-hero-caption">Actual SPY probability curve &middot; Historical example</p>
      </section>

      <section className="home-proof" aria-label="The research approach">
        <div><span>01</span><p><strong>Market-implied odds</strong>Built from options prices.</p></div>
        <div><span>02</span><p><strong>A historical reality check</strong>Compare forecasts with actual prices.</p></div>
        <div><span>03</span><p><strong>Quality in plain sight</strong>Inspect sources, freshness, and caveats.</p></div>
      </section>

      <section className="home-research home-section" id="research" aria-labelledby="research-title">
        <div className="home-section-heading">
          <div><p className="home-eyebrow">YOUR RESEARCH WORKBENCH</p><h2 id="research-title">Three ways to look deeper.</h2></div>
          <p>Move from a market question to a closer look at the evidence, in one place.</p>
        </div>
        <div role="tablist" aria-label="Dashboard features" className="home-tabs">
          {FEATURES.map((item, index) => <button key={item.id} type="button" role="tab"
            id={`${id}-tab-${index}`} aria-controls={`${id}-feature`} aria-selected={selected === index}
            tabIndex={selected === index ? 0 : -1} onClick={() => setSelected(index)}
            onKeyDown={(event) => {
              if (["ArrowRight", "ArrowLeft", "Home", "End"].includes(event.key)) {
                event.preventDefault();
                selectTab(event.key === "Home" ? 0 : event.key === "End" ? FEATURES.length - 1
                  : (selected + (event.key === "ArrowRight" ? 1 : -1) + FEATURES.length) % FEATURES.length);
              }
            }}><span className="home-tab-number">0{index + 1}</span>{item.name}</button>)}
        </div>
        <div className="home-feature" id={`${id}-feature`} role="tabpanel" aria-labelledby={`${id}-tab-${selected}`} tabIndex={0}>
          <div className="home-feature-copy">
            <p className="home-eyebrow">{feature.kicker}</p>
            <h3>{feature.title}</h3>
            <p>{feature.description}</p>
            <ul>{feature.points.map(point => <li key={point}>{point}</li>)}</ul>
            <Link className="home-text-link" to={feature.link}>{feature.action} <span aria-hidden="true">&rarr;</span></Link>
          </div>
          <figure className={`home-screenshot home-screenshot-${feature.id}`}>
            <button type="button" className="home-image-button" aria-label={`Enlarge ${feature.name} screenshot`} onClick={() => { setZoomed(true); imageDialog.current?.showModal(); }}>
              <img src={`/screenshots/${feature.image}`} alt={feature.alt} width={feature.id === "dacey" ? 600 : 2058}
                height={feature.id === "dacey" ? 1392 : feature.id === "theta" ? 1392 : 600} loading="lazy" />
            </button>
            <figcaption>{feature.caption}</figcaption>
            <button type="button" className="home-screenshot-link" onClick={() => { setZoomed(true); imageDialog.current?.showModal(); }}>View full screenshot <span aria-hidden="true">&rarr;</span></button>
          </figure>
        </div>
      </section>

      <section className="home-method" id="method" aria-labelledby="method-title">
        <div className="home-section">
          <div className="home-section-heading"><div><p className="home-eyebrow">FROM OBSERVATION TO INSIGHT</p><h2 id="method-title">Start with a question.<br />Keep the uncertainty visible.</h2></div>
            <p>A price target tells only part of the story. A distribution lets you ask what happens on either side of it.</p></div>
          <ol className="home-steps">
            <li><span>01 / OBSERVE</span><h3>Choose your window.</h3><p>Select a stock and the historical options data you want to study. Set a future target or revisit a past one.</p></li>
            <li><span>02 / RECONSTRUCT</span><h3>Read the distribution.</h3><p>The model fits the options-implied volatility curve and derives a price distribution. Inspect the range, skew, and downside it implies.</p></li>
            <li><span>03 / CHALLENGE</span><h3>Check the evidence.</h3><p>Compare past predictions with realized prices. Check data freshness and model assumptions before drawing a conclusion.</p></li>
          </ol>
        </div>
      </section>

      <section className="home-section home-difference" aria-labelledby="difference-title">
        <div><p className="home-eyebrow">WHAT MAKES IT DIFFERENT</p><h2 id="difference-title">More context.<br />Less false certainty.</h2><p>Bring price research and volatility research together, without hiding where the numbers came from.</p></div>
        <dl>
          <div><dt>A distribution, not a magic number.</dt><dd>Explore a range of outcomes and its tails, instead of treating a single price target as inevitable.</dd></div>
          <div><dt>A shortlist you can interrogate.</dt><dd>Theta candidates come with quote provenance and quality checks. A high IV/HV ratio is a starting point, not a sell signal.</dd></div>
          <div><dt>Research you can question.</dt><dd>Keep model outputs, historical comparisons, and an assistant with access to the same tools in one workspace.</dd></div>
        </dl>
      </section>

      <section className="home-faq home-section" aria-labelledby="faq-title">
        <h2 id="faq-title">Before you dive in.</h2>
        <details><summary>Are these probabilities a guarantee?</summary><p>No. They are risk-neutral, model-implied probabilities inferred from options prices, not calibrated real-world odds. The model's European-style pricing assumptions and dividend limitations matter. Review the calculation notes in the dashboard.</p></details>
        <details><summary>Does a high volatility premium mean I should sell?</summary><p>No. Earnings, distributions, stale prices, liquidity, and spreads can all affect the comparison. Theta Plays supports research; it does not identify risk-free trades or executable profits.</p></details>
        <details><summary>Do I need an account?</summary><p>You can explore Predictions and saved Theta scans without one. Any Google account can sign in to use Dacey and Market Context, subject to individual and shared usage limits.</p></details>
        <details><summary>Are the screenshots live market data?</summary><p>No. These are actual captures of the app using saved data. In the dashboard, use the observation dates, last-scan timestamps, and Data Health panel to assess freshness.</p></details>
      </section>

      <section className="home-close"><div><p className="home-eyebrow">TAKE A CLOSER LOOK</p><h2>What is the options market pricing in?</h2><Link className="home-primary" to="/app/predictions">Open Predictions <span aria-hidden="true">&rarr;</span></Link><Link className="home-text-link" to="/app/theta-plays">Browse Theta Plays <span aria-hidden="true">&rarr;</span></Link></div></section>
    </main>
    <footer className="home-footer"><Link to="/" className="home-wordmark">Decay <span>And Conquer</span></Link><p>Research tools, not investment advice. Options involve risk. Past results do not guarantee future outcomes.</p><a href="#home-title">Back to top &uarr;</a></footer>

    <dialog ref={imageDialog} className="home-image-dialog" aria-label={`${feature.name} screenshot`} onClose={() => setZoomed(false)}>
      <div><strong>{feature.name}</strong><button type="button" onClick={() => imageDialog.current?.close()}>Close</button></div>
      {zoomed && <img src={`/screenshots/${feature.image}`} alt={feature.alt} />}
      <p>{feature.caption}</p>
    </dialog>
  </div>;
}
