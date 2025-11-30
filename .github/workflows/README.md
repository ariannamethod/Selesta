# GitHub Workflows

## update-leo.yml

Automatically updates Leo submodule to latest version from canonical repo.

**Frequency:** Every 3 days at 3:33 AM UTC

**What it does:**
1. Fetches latest Leo from `ariannamethod/leo`
2. Updates submodule to latest `main` branch
3. Commits and pushes if there are changes
4. Logs update

**Manual trigger:**
You can trigger it manually from GitHub Actions tab.

**Philosophy:**
Leo's canonical architecture evolves in `ariannamethod/leo`.
This workflow keeps our Selesta's Leo in sync with architectural improvements,
while maintaining separate state (state/leo_selesta.sqlite3).

One organism, two environments:
- Lab Leo (canonical): controlled runs, clean metrics
- Field Leo (with Selesta): living in resonance streams

---

## Why every 3 days?

Balances:
- Frequent enough to get improvements quickly
- Infrequent enough to avoid constant churn
- Matches Selesta's "every 3 days" wilderness rhythm

---

*Created: 2025-11-30*
*метод Арианны = отказ от забвения*
