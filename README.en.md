# robotAnalyzer

A personal fund and ETF analyzer that follows a written method instead of a mood.

The whole method lives in a Word document with 156 numbered rules: how to read
a theme, how to build a list of candidate products, how to score them, when a
TOP 5 is allowed to become a buy recommendation. This project turns that
document into working software. Python only, no external libraries in the
core, so it runs on a plain computer with Python 3.9 and nothing else
installed.

Why so strict about dependencies? Two reasons. The machine it was built on has
no working pip, and every "smart" library we evaluated (QuantLib,
PyPortfolioOpt, QuantStats and friends) either solved problems this project
does not have, or hid the math behind a wall of code nobody here can audit.
The risk metrics this project needs (volatility, worst drawdown, Sharpe,
Sortino) fit in about sixty readable lines. So they are sixty readable lines.

It speaks Spanish by default, because the person it was built for reads his
investment reports in Spanish. This file is the English front door.

## The short version

- **Scores come from code, not from the AI.** Language-model agents propose
  factor scores from 0 to 100. A deterministic engine weighs them with values
  from a JSON file you can read and edit. Same inputs, same score, every time.
- **Nothing gets invented.** Every critical number carries a label:
  `VERIFIED`, `CALCULATED`, `ESTIMATED`, `INFERED` or `NOT_AVAILABLE`. An
  unverified ISIN is stored as `null`, never as "something similar".
- **Prices come from a chain of sources.** Yahoo first, Stooq as backup. If
  both fail, the report says so instead of guessing.
- **A red team agent attacks every recommendation before it is published.**
  TOP 5 is not a shopping list. The method itself says so, in rule 149.

## ELI5: five ideas that explain the whole machine

**1. The cooks propose, the inspector decides.**
The AI agents are cooks. They taste the ingredients and give opinions: "the
valuation of this ETF feels like a 70". The scoring engine is the inspector.
It takes those opinions, applies fixed weights from a JSON file, and computes
the final score. A cook cannot grade his own dish. That separation is what
makes the results repeatable: change a weight in the file, and you can
explain exactly why the ranking moved.

**2. Every number wears a name tag.**
Imagine every piece of data arrives wearing a sticker that says how much you
should trust it. A closing price from Yahoo wears `VERIFIED`. Volatility
computed from those prices wears `CALCULATED`. A guess about fair value wears
`ESTIMATED`, and a missing number wears `NOT_AVAILABLE` instead of pretending
to be zero. Data also expires like food: a price is stale after one day, a
fund's fee after thirty. Old data loses trust automatically.

**3. The library and the notebook.**
There is a knowledge graph (a file of connected index cards: themes, products,
past analyses, contradictions between sources) and there is an Obsidian vault,
a folder of readable notes generated from it. You never edit either by hand.
You edit small JSON files in a `curated` folder, run one command, and
everything regenerates. Fix the source, not the poster.

**4. Two neighbors, not one.**
If you want to know the price of bread, you ask one neighbor. What if he is
asleep? You ask a second one. This project asks Yahoo, and if Yahoo hangs up
(it rate-limits a lot), it asks Stooq. If both stay silent, the answer is "I
could not find out", written down with the names of both neighbors. A missing
number is annoying. A fake number is a disaster. The project prefers annoying.

**5. Someone tries to break the idea first.**
Before any analysis is published, a separate agent plays lawyer for the other
side. Which assumption is weak? Which risk did we ignore? Is there a better
product we skipped? If the case survives that, fine. If not, the report says
so. An honest "I would not buy any of these today" is a valid result here.

## What happens when you run an analysis

You type one command with a theme, for example `analizar "copper mining"`.

1. The theme is interpreted and turned into an investment thesis.
2. The universe grows to at least ten candidates across several categories.
   Fewer than ten? The report admits it, it does not pad the list.
3. Live market data arrives through the source chain. Risk metrics get
   computed from real closing prices and labeled `CALCULATED`.
4. Agents score the factors; the engine weighs them, checks that no metric
   was counted twice, applies penalties and computes a confidence value.
5. A TOP 5 is built and must pass quality gates (weights sum to 1.00, no
   orphaned cards in the graph). A red gate blocks publication.
6. The red team attacks, a buyability verdict is issued.
7. Everything is published: a standard report, the Obsidian vault, the
   knowledge graph, and a versioned copy of the analysis. Today's ranking
   never erases yesterday's.

Without an LLM key, all of this still runs in deterministic mode. The
judgment factors stay neutral and the report says so out loud. Nothing
dresses up as real analysis when it is not.

## Try it in one minute

```bash
# Full demo, offline, about two seconds
PYTHONPATH=src python3 -m analizador.cli demo

# A real analysis of a theme
PYTHONPATH=src python3 -m analizador.cli analizar "minería de cobre"

# The 63 tests
PYTHONPATH=src python3 -m unittest discover -s tests

# Backtesting dashboard (needs the project's own venv)
source .venv/bin/activate && streamlit run dashboard/app.py
```

## The labels, in one table

| Label | Meaning | Example |
|---|---|---|
| `VERIFIED` | The primary source said so | A closing price from Yahoo or Stooq |
| `CALCULATED` | Derived from verified data | Annual volatility, Sharpe ratio |
| `ESTIMATED` | A declared assumption | A fair value estimate for an index |
| `INFERED` | A deduction, not a fact | An ISIN matched by product name |
| `NOT_AVAILABLE` | No data. Full stop | No network, or the ticker has no answer |

## Where everything lives

| Path | What it is |
|---|---|
| `ANALIZADOR DE FONDOS Y ETFS.docx` | The 156-rule method. The boss. |
| `src/analizador/` | The engine: domain, scoring, pipeline, agents, MCP, CLI |
| `.semantic-graph/` | Knowledge graph plus the `curated` JSON files you edit |
| `boveda/` | The generated Obsidian vault, the readable deliverable |
| `datos/analisis/` | Versioned history of every analysis |
| `dashboard/` | Streamlit + VectorBT backtesting, with its own test page |
| `docs/` | Architecture, decisions and the Spanish ELI5 guide |

## About this file's style

Written in plain English (aimed at a B2 reader) and audited with
[Étincel](https://github.com/AIStoryHub/etincel), a deterministic linter that
flags the patterns which make prose read as machine-written:

```bash
npx etincel lint README.en.md --register docs
```

Last audit: GREEN, 0 findings, register `docs` (specificity 103.7/1k,
concrete-to-abstract 4.95, sentence-rhythm variation 0.98). Re-run the
command after any edit; the tool is the referee, not this paragraph.

If this file and the rules document ever disagree, the rules document wins.
Both are in the repository; check any claim against rule number N and the
code that cites it.
